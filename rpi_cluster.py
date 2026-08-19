#!/usr/bin/env python3
"""
rpi_cluster.py — RPI_Cluster single-entry-point regulatory intelligence scraper.

    python rpi_cluster.py [options]

Orchestrates every country extractor in a fixed API-first / Selenium-last order,
normalizes each result set to the canonical 19-field schema, writes per-country
CSVs, consolidates into a master file, and builds an xlsx executive-summary report.

The pipeline is LOCAL-ONLY: extracted data never leaves the machine. Notion/Airtable
push and SMTP delivery were removed on 16/08/2026 because company compliance does not
permit automated connectors — results are handed over by copying from the generated
workbook into the team's consolidated file.

See requirements.txt for dependencies. The orchestrator itself imports only the
standard library; each extractor pulls its heavy dependency (requests / selenium /
openpyxl) lazily, so a missing one degrades that country to an ERROR row instead
of crashing the run.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import logging
import os
import sys
import traceback
from datetime import date

import config
import consolidate as consolidate_mod
import normalize
import postfilter
import presence
import report

# ── Make stdout/stderr UTF-8 so the emoji summary never crashes a cp1252 console.
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LOG = logging.getLogger("rpi")

# Status icons (schema / run-summary rules).
ICON_OK = "✅"
ICON_WARN = "⚠️"
ICON_FAIL = "❌"
ICON_SKIP = "🔄"

# ── Extractor registry, in execution order ────────────────────────────────────
# group       : display row in the run summary
# cc          : value matched by --country
# selenium    : requires a browser (skipped under --no-selenium)
# disabled    : reason string — the extractor is quarantined and never runs
EXTRACTORS = [
    {"key": "ema",            "label": "EMA",            "group": "EMA (EU)",     "cc": "EMA", "module": "extractors.ema",            "outfile": config.OUTPUT_FILES["ema"],            "selenium": False},
    {"key": "fda",            "label": "FDA",            "group": "FDA (US)",     "cc": "FDA", "module": "extractors.fda",            "outfile": config.OUTPUT_FILES["fda"],            "selenium": False},
    {"key": "co_approvals",   "label": "Colombia APR",   "group": "Colombia",     "cc": "CO",  "module": "extractors.co_approvals",   "outfile": config.OUTPUT_FILES["co_approvals"],   "selenium": False},
    {"key": "hn",             "label": "Honduras",       "group": "Honduras",     "cc": "HN",  "module": "extractors.hn",             "outfile": config.OUTPUT_FILES["hn"],             "selenium": False},
    {"key": "sv",             "label": "El Salvador",    "group": "El Salvador",  "cc": "SV",  "module": "extractors.sv",             "outfile": config.OUTPUT_FILES["sv"],             "selenium": False},
    {"key": "gt",             "label": "Guatemala",      "group": "Guatemala",    "cc": "GT",  "module": "extractors.gt",             "outfile": config.OUTPUT_FILES["gt"],             "selenium": True},
    {"key": "do",             "label": "Dominican Rep",  "group": "Dom. Rep.",    "cc": "DO",  "module": "extractors.do",             "outfile": config.OUTPUT_FILES["do"],             "selenium": True},
    # Rebuilt 16/08/2026 against Registrelo's own public report API (the previous
    # report-download approach silently parsed Honduras' workbook — see cr.py).
    {"key": "cr",             "label": "Costa Rica",     "group": "Costa Rica",   "cc": "CR",  "module": "extractors.cr",             "outfile": config.OUTPUT_FILES["cr"],             "selenium": True},
    # OUT OF SCOPE 16/08/2026 (business decision). DIGEMID sits behind a Cloudflare
    # managed challenge; clearing it needs a stealth/undetected driver, which is a
    # compliance question the company has not signed off on. The extractors are kept
    # intact — only disabled — so Peru can be re-enabled by deleting these two
    # "disabled" keys once Legal/IT rules on it.
    {"key": "pe_approvals",   "label": "Peru APR",       "group": "Peru",         "cc": "PE",  "module": "extractors.pe_approvals",   "outfile": config.OUTPUT_FILES["pe_approvals"],   "selenium": True,
     "disabled": "fuera de alcance — pendiente decisión de compliance sobre el bypass anti-bot"},
    {"key": "pe_submissions", "label": "Peru SUB",       "group": "Peru",         "cc": "PE",  "module": "extractors.pe_submissions", "outfile": config.OUTPUT_FILES["pe_submissions"], "selenium": True,
     "disabled": "fuera de alcance — pendiente decisión de compliance sobre el bypass anti-bot"},
    # OUT OF SCOPE 18/08/2026 (business decision). Colombia filings are tracked by the
    # Regulatory Affairs team from an INVIMA transparency document they maintain
    # themselves, which carries the recent movements this extractor never could: its
    # Socrata source (t2gj-yg8s) is a historical archive that stops at 11/07/2024, so
    # nothing it returned could ever land inside the 30-day alert window. Keeping it on
    # would push 565 stale rows into the consolidated and collide with the team's own
    # record. The extractor and its tests stay intact — delete this "disabled" key to
    # bring it back.
    {"key": "co_submissions", "label": "Colombia SUB",   "group": "Colombia",     "cc": "CO",  "module": "extractors.co_submissions", "outfile": config.OUTPUT_FILES["co_submissions"], "selenium": False,
     "disabled": "fuera de alcance — los trámites de Colombia los lleva el equipo en su documento de transparencia"},
    {"key": "ec",             "label": "Ecuador",        "group": "Ecuador",      "cc": "EC",  "module": "extractors.ec",             "outfile": config.OUTPUT_FILES["ec"],             "selenium": False},
]

# Summary display order and which groups never carry submissions.
GROUP_ORDER = ["EMA (EU)", "FDA (US)", "Colombia", "Honduras", "El Salvador",
               "Guatemala", "Dom. Rep.", "Costa Rica", "Peru", "Ecuador"]
GROUP_SUBMISSIONS_NA = {"Honduras", "El Salvador", "Guatemala", "Dom. Rep."}

# Tier A = the HTTP-only, browser-free, human-free sources that run reliably
# unattended (no CAPTCHA, no ChromeDriver, no manual step). The natural target for
# a scheduled routine. Excludes Ecuador (rate-limited + unconfirmed endpoints).
TIER_A_KEYS = {"ema", "fda", "co_approvals", "sv", "hn"}


# ── .env loading (no external dependency) ─────────────────────────────────────
def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logging(output_dir: str) -> str:
    log_path = os.path.join(output_dir, f"rpi_run_{date.today():%d%m%Y}.log")
    LOG.setLevel(logging.DEBUG)
    LOG.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                      "%Y-%m-%d %H:%M:%S"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    LOG.addHandler(fh)
    LOG.addHandler(ch)
    return log_path


# ── CSV writer ────────────────────────────────────────────────────────────────
def write_canonical_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=config.CANONICAL_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({f: (row.get(f) if row.get(f) is not None else "")
                             for f in config.CANONICAL_FIELDS})


# ── Argument parsing ──────────────────────────────────────────────────────────
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="rpi_cluster.py",
        description="RPI_Cluster — regulatory intelligence multi-country scraper.")
    p.add_argument("--output-dir", default=None,
                   help="Local folder for CSV output (default: ./output or $RPI_OUTPUT_DIR)")
    p.add_argument("--country", default=None,
                   help="Run only one country: PE, CO, SV, GT, HN, DO, CR, EC, EMA, FDA")
    p.add_argument("--molecule", default=None,
                   help="Run only one molecule (INN/LATAM term) instead of the full list")
    p.add_argument("--no-selenium", action="store_true",
                   help="Skip Selenium-dependent countries and print a warning")
    p.add_argument("--tier-a", action="store_true",
                   help="Run only the reliable HTTP sources (EMA, FDA, Colombia, "
                        "El Salvador, Honduras) — the unattended/scheduled preset")
    p.add_argument("--no-ec", action="store_true",
                   help="Exclude Ecuador from a full run (it runs by default; its bulk "
                        "report download adds ~25-45s). Tier-A never includes Ecuador.")
    p.add_argument("--include-ec", action="store_true",
                   help="Deprecated/no-op: Ecuador now runs by default in a full run.")
    p.add_argument("--no-report", action="store_true",
                   help="Skip generating the xlsx executive-summary report")
    p.add_argument("--fda-api-key", default=None, help="OpenFDA API key (raises rate limit)")
    p.add_argument("--headless", action="store_true",
                   help="Run Selenium browsers headless (not recommended for the Peru CAPTCHA step)")
    p.add_argument("--non-interactive", action="store_true",
                   help="Never pause for manual input (CAPTCHA steps proceed/skip automatically)")
    p.add_argument("--pe-stealth", action="store_true",
                   help="Peru: use SeleniumBase UC mode to auto-clear the Cloudflare "
                        "challenge (needs `pip install seleniumbase` + a display)")
    return p.parse_args(argv)


def _row_key(row: dict) -> tuple:
    """Identity of a record across runs — the same key deduplicate() uses."""
    return (row.get("registration_number", ""), row.get("country_code", ""),
            row.get("record_type", ""))


def _restore_first_seen(canonical: list[dict], previous: list[dict]) -> int:
    """Carry each already-known record's original extraction_date forward.

    ``extraction_date`` is stamped at normalization time, so re-extracting a record
    that has been in the file for months would re-date it as if it were new. Rows that
    already exist keep the date they were first written; only genuinely new records
    carry the current run's date. Returns how many rows were restored.
    """
    if not previous:
        return 0
    first_seen = {}
    for row in previous:
        date_seen = (row.get("extraction_date") or "").strip()
        if date_seen:
            first_seen.setdefault(_row_key(row), date_seen)
    restored = 0
    for row in canonical:
        original = first_seen.get(_row_key(row))
        if original and original != row.get("extraction_date"):
            row["extraction_date"] = original
            restored += 1
    return restored


# ── Per-extractor execution ───────────────────────────────────────────────────
def run_extractor(entry: dict, molecules: list[dict], ex_config: dict,
                  output_dir: str, merge_hint: bool = False) -> dict:
    """Run one extractor; return a result record for the summary.

    Statuses: OK (rows, no errors) · PARTIAL (rows, some fetch errors) ·
    EMPTY (no rows, no errors) · FAILED (no rows, handled errors) ·
    ERROR (unhandled exception).

    File-write policy: a clean full run overwrites the per-country CSV
    (snapshot). When the run was narrowed (--molecule), had errors, or came back
    empty, the new rows are MERGED with the existing file instead, so a flaky
    network or a filtered run can never wipe out yesterday's good data.
    """
    result = {"key": entry["key"], "label": entry["label"], "group": entry["group"],
              "country_code": ex_config.get("country_code"),
              "approvals": 0, "submissions": 0, "status": "EMPTY", "rows": []}

    LOG.info("→ %s starting…", entry["label"])
    try:
        module = importlib.import_module(entry["module"])
        raw_rows = module.extract(molecules, ex_config)
        errors = ex_config.get("partial_errors") or []

        canonical = normalize.normalize_rows(
            raw_rows or [],
            country_code=ex_config.get("country_code"),
            record_type=ex_config.get("record_type"),
            source_url=ex_config.get("source_url"),
        )
        canonical = normalize.deduplicate(canonical)

        # Indication / sub-type post-filters (Tadalafil PAH, Ranibizumab biosimilar,
        # Bevacizumab ophthalmic). Rows for other molecules pass through untouched.
        canonical, dropped = postfilter.apply_post_filters(canonical, molecules)
        if dropped:
            detail = ", ".join(f"{t}: {n}" for t, n in sorted(dropped.items()))
            LOG.info("  %s post-filter dropped %d row(s) [%s]",
                     entry["label"], sum(dropped.values()), detail)

        # Decide what lands in the per-country file.
        out_path = os.path.join(output_dir, entry["outfile"])
        previous = []
        if os.path.exists(out_path):
            try:
                previous = consolidate_mod.load_csv(out_path)
            except Exception:
                previous = []

        # Keep each record's ORIGINAL extraction_date, so the column answers "when did
        # this registration first appear" rather than "when did we last run". Without
        # this every row is restamped on every run, and a genuinely new competitor
        # approval becomes indistinguishable from one tracked for a year — which is
        # precisely the signal the downstream alerting depends on. Every other field
        # still refreshes, so status/date corrections at the source do come through.
        restored = _restore_first_seen(canonical, previous)
        if restored:
            LOG.info("  %s: %d record(s) keep their original extraction_date",
                     entry["label"], restored)

        file_rows = canonical
        if (merge_hint or errors or not canonical) and previous:
            # New rows win ties (same extraction_date) in deduplicate().
            file_rows = normalize.deduplicate(previous + canonical)
            if len(file_rows) > len(canonical):
                LOG.info("  %s: merged with previous output (%d extracted, "
                         "file keeps %d rows)", entry["label"],
                         len(canonical), len(file_rows))
        write_canonical_csv(file_rows, out_path)

        result["rows"] = canonical
        result["approvals"] = sum(1 for r in canonical if r.get("record_type") == "APPROVAL")
        result["submissions"] = sum(1 for r in canonical if r.get("record_type") == "SUBMISSION")
        if canonical:
            result["status"] = "PARTIAL" if errors else "OK"
        else:
            result["status"] = "FAILED" if errors else "EMPTY"
        if errors:
            LOG.warning("  %s reported %d error(s); first: %s",
                        entry["label"], len(errors), errors[0])
        LOG.info("  %s done: %d approvals, %d submissions → %s",
                 entry["label"], result["approvals"], result["submissions"], entry["outfile"])
    except Exception:
        result["status"] = "ERROR"
        LOG.error("  %s FAILED:\n%s", entry["label"], traceback.format_exc())
    return result


# ── Run summary ───────────────────────────────────────────────────────────────
# Column inner widths (content area between the ║ separators).
_COLW = [14, 10, 11, 16]
_SEGW = [w + 2 for w in _COLW]  # +1 space of padding on each side


def _vwidth(s: str) -> int:
    """Display width counting emoji icons as 2 cells and variation selectors as 0."""
    w = 0
    for ch in s:
        if ch == "️":  # variation selector — zero width
            continue
        o = ord(ch)
        if o in (0x2705, 0x274C, 0x26A0) or o >= 0x1F000:
            w += 2
        else:
            w += 1
    return w


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _vwidth(s))


def _border(left: str, mid: str, right: str) -> str:
    return left + mid.join("═" * w for w in _SEGW) + right


def _full_border(left: str, right: str) -> str:
    return left + "═" * (sum(_SEGW) + len(_SEGW) - 1) + right


def _data_row(c0: str, c1: str, c2: str, c3: str) -> str:
    cells = [_pad(c0, _COLW[0]), _pad(c1, _COLW[1]), _pad(c2, _COLW[2]), _pad(c3, _COLW[3])]
    return "║ " + " ║ ".join(cells) + " ║"


def _group_label(status_set: set, records: int, ran: bool) -> str:
    if not ran:
        return "—  not run"
    if status_set == {"DISABLED"}:
        return "⛔ Disabled"
    if "ERROR" in status_set:
        return f"{ICON_FAIL} Error"
    if "PARTIAL" in status_set or ("FAILED" in status_set and records > 0):
        return f"{ICON_WARN} Partial"
    if records > 0:
        return f"{ICON_OK} OK"
    if status_set == {"SKIPPED"}:
        return f"{ICON_SKIP} Skipped"
    if "FAILED" in status_set:
        return f"{ICON_WARN} Failed"
    return f"{ICON_WARN} Empty"


def build_summary(results: list[dict], consolidated: bool) -> str:
    agg: dict[str, dict] = {g: {"approvals": 0, "submissions": 0, "statuses": set(), "ran": False}
                            for g in GROUP_ORDER}
    for r in results:
        g = agg[r["group"]]
        g["approvals"] += r["approvals"]
        g["submissions"] += r["submissions"]
        g["statuses"].add(r["status"])
        g["ran"] = True

    inner = sum(_SEGW) + len(_SEGW) - 1
    lines = [_full_border("╔", "╗")]
    lines.append("║" + _pad(f"  RPI Extraction Run — {date.today():%d/%m/%Y}", inner) + "║")
    lines.append(_border("╠", "╦", "╣"))
    lines.append(_data_row("Country", "Approvals", "Submissions", "Status"))
    lines.append(_border("╠", "╬", "╣"))

    total_a = total_s = 0
    for g in GROUP_ORDER:
        a, s, ran = agg[g]["approvals"], agg[g]["submissions"], agg[g]["ran"]
        total_a += a
        total_s += s
        sub_disp = "N/A" if g in GROUP_SUBMISSIONS_NA else str(s)
        lines.append(_data_row(g, str(a), sub_disp,
                               _group_label(agg[g]["statuses"], a + s, ran)))

    lines.append(_border("╠", "╩", "╣"))
    cons_txt = f"Consolidated {ICON_OK}" if consolidated else f"Not consolidated {ICON_WARN}"
    total_line = f"  TOTAL: {total_a} approvals · {total_s} submissions · {cons_txt}"
    lines.append("║" + _pad(total_line, inner) + "║")
    lines.append(_full_border("╚", "╝"))
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    load_dotenv()
    args = parse_args(argv)

    output_dir = (args.output_dir or os.environ.get("RPI_OUTPUT_DIR")
                  or config.DEFAULT_OUTPUT_DIR)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    download_dir = os.path.join(output_dir, "_downloads")
    os.makedirs(download_dir, exist_ok=True)

    log_path = setup_logging(output_dir)
    LOG.info("RPI_Cluster run — %s", date.today().strftime("%d/%m/%Y"))
    LOG.info("Output directory: %s", output_dir)

    # Molecule + country selection.
    molecules = config.molecules_for(args.molecule)
    if args.molecule:
        LOG.info("Molecule filter: %s → %d molecule(s)", args.molecule, len(molecules))
    country = args.country.upper() if args.country else None

    # Shared HTTP sessions for the API extractors.
    try:
        api_session = config.build_session()
    except Exception:
        api_session = None

    selected = list(EXTRACTORS)
    if args.tier_a:
        selected = [e for e in selected if e["key"] in TIER_A_KEYS]
        LOG.info("Tier-A preset: %s", ", ".join(e["label"] for e in selected))
    if country:
        selected = [e for e in selected if e["cc"] == country]
    elif args.no_ec:
        # Opt-out: drop Ecuador's slow ~tens-of-MB bulk download from this full run.
        selected = [e for e in selected if e["key"] != "ec"]
        LOG.info("Ecuador excluded (--no-ec).")
    elif not args.tier_a and any(e["key"] == "ec" for e in selected):
        # Ecuador now runs by default in a full run (it has no per-molecule search, so
        # it bulk-downloads ARCSA's ~44MB registry and filters in memory: ~25-45s).
        LOG.info("Ecuador included in full run (bulk report ~25-45s; --no-ec to skip).")
    if country and not selected:
        LOG.error("Unknown --country '%s'. Valid: PE CO SV GT HN DO CR EC EMA FDA", country)
        return 2

    results: list[dict] = []
    for entry in selected:
        cc_code = {"ema": "EU", "fda": "US"}.get(entry["key"], entry["cc"])
        if entry.get("disabled"):
            # Quarantined: never run, and never write/merge a CSV for it, so a known
            # bad extractor cannot keep contaminating the consolidated output.
            LOG.warning("⛔ %s DESACTIVADO — %s", entry["label"], entry["disabled"])
            results.append({"key": entry["key"], "label": entry["label"], "group": entry["group"],
                            "country_code": cc_code, "approvals": 0, "submissions": 0,
                            "status": "DISABLED", "rows": []})
            continue
        if entry["selenium"] and args.no_selenium:
            LOG.warning("⏭  %s skipped (--no-selenium)", entry["label"])
            results.append({"key": entry["key"], "label": entry["label"], "group": entry["group"],
                            "country_code": cc_code, "approvals": 0, "submissions": 0,
                            "status": "SKIPPED", "rows": []})
            continue

        # Per-extractor download folder. A single shared folder let one country's
        # workbook be picked up as another's "download" (see the CR/HN incident);
        # isolating them makes that class of contamination structurally impossible.
        entry_download_dir = os.path.join(download_dir, entry["key"])
        os.makedirs(entry_download_dir, exist_ok=True)

        ex_config = {
            "output_dir": output_dir,
            "download_dir": entry_download_dir,
            "headless": args.headless,
            "non_interactive": args.non_interactive,
            "session": api_session,
            "fda_api_key": args.fda_api_key or os.environ.get("FDA_API_KEY"),
            "country_code": cc_code,
            "source_url": config.SOURCE_URLS.get(entry["key"]),
            "record_type": None,
            "partial_errors": [],
            "no_selenium": args.no_selenium,
            "pe_stealth": args.pe_stealth,
        }
        results.append(run_extractor(entry, molecules, ex_config, output_dir,
                                     merge_hint=bool(args.molecule)))

    # Presence rows: for novel molecules with no data in countries we searched
    # successfully, emit a NULL-filled "we looked, found nothing" row. Written to
    # its own RPI*_canonical.csv so consolidation picks it up.
    real_rows = normalize.deduplicate([r for res in results for r in res["rows"]])
    searched_ccs = {res.get("country_code") for res in results
                    if res["status"] in ("OK", "EMPTY", "PARTIAL")}
    presence_rows = presence.generate_presence_rows(real_rows, molecules, searched_ccs)
    if presence_rows:
        write_canonical_csv(presence_rows, os.path.join(output_dir, "RPIPRESENCE_canonical.csv"))
        LOG.info("Presence rows: %d (novel molecules with no data in %d searched "
                 "countries)", len(presence_rows), len(searched_ccs))

    # Consolidation (skipped with a warning if < 2 country files exist).
    consolidated_path = consolidate_mod.consolidate(output_dir)

    # Unmapped status log.
    unmapped_path = os.path.join(output_dir, "unmapped_status.log")
    unmapped_count = normalize.write_unmapped_log(unmapped_path)

    all_rows = real_rows + presence_rows

    # Executive-summary xlsx report (generated by default when there is data).
    #
    # It is built from the CONSOLIDATED file, not from this run's in-memory rows.
    # Those two differ whenever a source comes back empty: the merge-don't-clobber
    # logic keeps that country's previous CSV on disk (so it stays in the
    # consolidated), but it contributed 0 rows to this run. Reporting on the
    # in-memory rows silently dropped the whole country from the workbook — e.g. a
    # run where datos.gov.co was republishing produced a report with 8 countries and
    # no Colombia at all, while the consolidated CSV correctly carried its 656 rows.
    # The report must describe the same dataset the CSV does.
    report_path = None
    if not args.no_report:
        try:
            if consolidated_path:
                report_path = report.generate(output_dir)      # reads the consolidated
            elif all_rows:
                report_path = report.generate(output_dir, rows=all_rows)
            if report_path:
                LOG.info("Report: wrote %s", os.path.basename(report_path))
        except Exception as exc:  # noqa: BLE001 - reporting must not crash the run
            LOG.error("Report generation failed (non-fatal): %s", exc)

    # NOTE: this pipeline is deliberately LOCAL-ONLY. Extracted data never leaves the
    # machine — no Notion/Airtable push, no SMTP delivery. Company compliance does not
    # permit automated connectors, so results are handed over by opening the generated
    # xlsx/CSV and copying into the team's consolidated workbook.

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print(build_summary(results, consolidated_path is not None))
    if consolidated_path:
        print(f"Output: {consolidated_path}")
    if report_path:
        print(f"Report: {report_path}")
    print(f"Unmapped statuses: {unmapped_count}"
          + (f" (see {unmapped_path})" if unmapped_count else ""))
    print(f"Full log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
