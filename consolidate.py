"""
consolidate.py — Merge all per-country canonical CSVs into one master file.

Callable two ways:

    # From the orchestrator
    import consolidate
    path = consolidate.consolidate(output_dir)

    # Standalone
    python consolidate.py --input-dir ./output --output-dir ./output

Reads every ``RPI*_canonical.csv`` in the input directory (the consolidated file is
not named ``*_canonical.csv`` and is therefore never re-ingested), deduplicates on
(registration_number, country_code, record_type) keeping the most recently extracted
row, and writes **``RPI_CONSOLIDATED.csv``** — a stable name, overwritten each run.

The name is deliberately stable: the file is uploaded to a SharePoint location that a
Power Automate / Fabric dataflow reads from a fixed path. A dated filename would make
someone rename the file by hand before every upload. A dated copy is still archived
under ``_history/`` so past runs stay auditable without cluttering the folder the
uploader looks at.

Per the spec, consolidation is skipped (with a warning) when fewer than two
country files are present.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import date
from typing import Optional

from normalize import CANONICAL_FIELDS, deduplicate

# Stable filename for the file that feeds SharePoint/Fabric, and the subfolder that
# keeps the dated copies. Both are referenced by report.py, so they live here.
CONSOLIDATED_NAME = "RPI_CONSOLIDATED.csv"
HISTORY_DIRNAME = "_history"


def load_csv(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k: (v.strip() if isinstance(v, str) and v.strip() else None)
                         for k, v in row.items()})
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({f: (row.get(f) if row.get(f) is not None else "")
                             for f in CANONICAL_FIELDS})


def summarize(rows: list[dict]) -> None:
    country_stats: dict[str, dict] = defaultdict(
        lambda: {"APPROVAL": 0, "SUBMISSION": 0, "CANCELLATION": 0, "other": 0})
    for row in rows:
        cc = row.get("country_code") or "UNKNOWN"
        rt = row.get("record_type") or "other"
        if rt in country_stats[cc]:
            country_stats[cc][rt] += 1
        else:
            country_stats[cc]["other"] += 1

    print("\n" + "=" * 62)
    print(f"  RPI Consolidation Summary — {date.today():%d/%m/%Y}")
    print("=" * 62)
    print(f"  {'Country':<14}{'Approvals':>11}{'Submissions':>13}{'Other':>8}")
    print("-" * 62)
    total_a = total_s = 0
    for cc in sorted(country_stats):
        a = country_stats[cc]["APPROVAL"]
        s = country_stats[cc]["SUBMISSION"]
        o = country_stats[cc]["CANCELLATION"] + country_stats[cc]["other"]
        total_a += a
        total_s += s
        flag = "OK " if (a + s) > 0 else "!! "
        print(f"  {flag}{cc:<11}{a:>11}{s:>13}{o:>8}")
    print("-" * 62)
    print(f"  {'TOTAL':<14}{total_a:>11}{total_s:>13}")
    print(f"  Grand total records: {len(rows)}")
    print("=" * 62)

    if rows:
        print("\n  Null rate per field:")
        n = len(rows)
        for field in CANONICAL_FIELDS:
            null_count = sum(1 for r in rows if not r.get(field))
            pct = null_count / n * 100
            bar = "#" * int(pct / 5)
            print(f"    {field:<23}{pct:6.1f}%  {bar}")
    print()


def consolidate(output_dir: str, input_dir: Optional[str] = None,
                quiet: bool = False) -> Optional[str]:
    """Merge per-country canonical CSVs into the master consolidated file.

    Returns the path to the written file, or ``None`` when consolidation was
    skipped (fewer than two country files present).
    """
    input_dir = input_dir or output_dir
    pattern = os.path.join(input_dir, "RPI*_canonical.csv")
    files = sorted(glob.glob(pattern))

    if len(files) < 2:
        print(f"  [consolidate] WARNING: only {len(files)} country file(s) found "
              f"in {input_dir} — need at least 2. Skipping consolidation.")
        return None

    if not quiet:
        print(f"  [consolidate] Found {len(files)} canonical file(s):")
    all_rows: list[dict] = []
    for f in files:
        rows = load_csv(f)
        if not quiet:
            print(f"    {os.path.basename(f)}: {len(rows)} rows")
        all_rows.extend(rows)

    deduped = deduplicate(all_rows)
    if not quiet:
        print(f"  [consolidate] {len(all_rows)} rows -> {len(deduped)} after dedup")

    # The primary output has a STABLE name and is overwritten every run. It feeds a
    # SharePoint document that a Power Automate / Fabric flow ingests on a fixed path,
    # so a date in the filename would force whoever uploads it to rename the file by
    # hand each time — a manual step that eventually gets done wrong and silently
    # breaks the refresh.
    out_file = os.path.join(output_dir, CONSOLIDATED_NAME)
    write_csv(deduped, out_file)
    print(f"  [consolidate] Wrote {out_file}")

    # A dated copy is kept out of the way for traceability: this is regulatory data,
    # so "what did we report on date X" has to remain answerable. It lives in a
    # subfolder precisely so the output folder holds exactly ONE consolidated file
    # and nobody has to choose which one to upload.
    try:
        history_dir = os.path.join(output_dir, HISTORY_DIRNAME)
        os.makedirs(history_dir, exist_ok=True)
        write_csv(deduped, os.path.join(
            history_dir, f"RPI_CONSOLIDATED_{date.today():%d%m%Y}.csv"))
    except Exception as exc:  # noqa: BLE001 - history must never break the run
        print(f"  [consolidate] WARNING: could not archive a dated copy: {exc}")

    if not quiet:
        summarize(deduped)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate RPI canonical CSVs")
    parser.add_argument("--input-dir", required=True,
                        help="Directory containing RPI*_canonical.csv files")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to write the consolidated file")
    args = parser.parse_args()

    result = consolidate(args.output_dir, input_dir=args.input_dir)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
