"""
normalize.py — RPI canonical normalization helpers (shared by every extractor).

Extractors return *raw* dicts. All canonical transformation — status mapping,
date parsing, null fill, uppercasing, PK enforcement — happens here, never inside
the extractors.

Typical use from the orchestrator:

    from normalize import normalize_rows, deduplicate, CANONICAL_FIELDS

    canonical = normalize_rows(
        raw_rows,
        country_code="CO",
        record_type="APPROVAL",
        molecule_search_term="REGORAFENIB",
        source_url="https://www.datos.gov.co/resource/i7cb-raxc.json",
    )
    canonical = deduplicate(canonical)

A raw row may carry its own ``country_code``/``record_type``/``molecule_search_term``/
``source_url`` keys. When present these win over the keyword defaults passed to
``normalize_rows`` — this lets a single extractor (e.g. EMA) emit both APPROVAL and
SUBMISSION rows, or per-row molecule terms, in one call.

This module is import-safe with the standard library only (python-dateutil is an
optional accelerator, not a hard dependency).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from typing import Optional

# Optional: python-dateutil gives us a forgiving fallback parser. Never required.
try:  # pragma: no cover - exercised only when the package is installed
    from dateutil import parser as _dateutil_parser  # type: ignore
except Exception:  # ImportError or partial install
    _dateutil_parser = None


# ── Canonical field order (must match schema §9 exactly) ──────────────────────
CANONICAL_FIELDS = [
    "registration_number",
    "country_code",
    "health_authority",
    "record_type",
    "product_name",
    "api",
    "concentration",
    "dosage_form",
    "applicant",
    "manufacturer",
    "manufacturer_country",
    "status",
    "process_type",
    "submission_date",
    "approval_date",
    "expiration_date",
    "molecule_search_term",
    "source_url",
    "extraction_date",
]

# ── Health authority lookup (schema §4) ───────────────────────────────────────
HA_MAP = {
    "PE": "DIGEMID",
    "EC": "ARCSA",
    "CO": "INVIMA",
    "CR": "MCCSS-DRTM",
    "SV": "SRS",
    "GT": "MSPAS",
    "HN": "ARSA",
    "DO": "DIGEMAPS",
    "EU": "EMA",
    "US": "FDA",
}

# ── Status normalization (schema §5) ──────────────────────────────────────────
# Keys are compared case-insensitively after stripping. Canonical values are also
# included as identity mappings so an extractor may pre-derive a status (e.g. the
# DR rule, or Honduras' hardcoded APPROVED) without it being logged as "unmapped".
_STATUS_MAP = {
    # ── identity (pre-canonicalized by an extractor) ──
    "approved": "APPROVED",
    "pending": "PENDING",
    "rejected": "REJECTED",
    "expired": "EXPIRED",
    "suspended": "SUSPENDED",
    "canceled": "CANCELED",
    # ── APPROVED ──
    "vigente": "APPROVED",
    "activo": "APPROVED",
    "activa": "APPROVED",
    "aprobado": "APPROVED",
    "aprobada": "APPROVED",
    "registered": "APPROVED",
    "authorised": "APPROVED",
    "authorized": "APPROVED",
    "authorised (full)": "APPROVED",
    "finalizado": "APPROVED",      # INVIMA trámite (co_submissions estado_tramite) concluded
    "ap": "APPROVED",  # FDA submission_status code
    # ── PENDING ──
    "en trámite": "PENDING",
    "en tramite": "PENDING",
    "pendiente": "PENDING",
    "under review": "PENDING",
    "under evaluation": "PENDING",
    "en proceso": "PENDING",       # INVIMA trámite in progress
    "en curso": "PENDING",         # INVIMA trámite (co_submissions estado_tramite) in progress
    "en evaluacion": "PENDING",
    "submitted": "PENDING",
    "in review": "PENDING",
    "opinion": "PENDING",          # EMA: positive/negative CHMP opinion, pre-decision
    "opinion under re-examination": "PENDING",  # EMA
    "ta": "PENDING",  # FDA Tentative Approval
    "pr": "PENDING",  # FDA Pending Review
    # ── REJECTED ──
    "denegado": "REJECTED",
    "denegada": "REJECTED",
    "rechazado": "REJECTED",
    "rechazada": "REJECTED",
    "rejected": "REJECTED",
    "refused": "REJECTED",
    "withdrawn by applicant": "REJECTED",
    "rf": "REJECTED",  # FDA Refuse to File
    # ── EXPIRED ──
    "vencido": "EXPIRED",
    "vencida": "EXPIRED",
    "expired": "EXPIRED",
    "caducado": "EXPIRED",
    "caducada": "EXPIRED",
    "lapsed": "EXPIRED",  # EMA: marketing authorisation lapsed
    # ── SUSPENDED ──
    "suspendido": "SUSPENDED",
    "suspendida": "SUSPENDED",
    "suspended": "SUSPENDED",
    # ── CANCELED ──
    "cancelado": "CANCELED",
    "cancelada": "CANCELED",
    "canceled": "CANCELED",
    "cancelled": "CANCELED",
    "revoked": "CANCELED",
    "anulado": "CANCELED",
    "anulada": "CANCELED",
    "withdrawn": "CANCELED",
    "application withdrawn": "CANCELED",  # EMA post-auth phrasing
    "withdrawn from rolling review": "CANCELED",  # EMA
    "wd": "CANCELED",  # FDA Withdrawn
}

# Accumulates {"raw": ..., "country_code": ...} for every unrecognized status.
_UNMAPPED_LOG: list[dict] = []


def normalize_status(raw: Optional[str], country_code: str = "") -> Optional[str]:
    """Map a raw health-authority status to one of the six canonical values.

    Unknown / empty values return ``None`` and are accumulated for end-of-run
    reporting via :func:`get_unmapped_statuses` / :func:`write_unmapped_log`.
    """
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    mapped = _STATUS_MAP.get(key)
    if mapped is None:
        _UNMAPPED_LOG.append({"raw": str(raw).strip(), "country_code": country_code})
    return mapped


def get_unmapped_statuses() -> list[dict]:
    """Return the accumulated list of unrecognized {raw, country_code} statuses."""
    return _UNMAPPED_LOG.copy()


def reset_unmapped_statuses() -> None:
    """Clear the unmapped-status accumulator (useful for tests / repeat runs)."""
    _UNMAPPED_LOG.clear()


def write_unmapped_log(path: str) -> int:
    """Write aggregated unmapped statuses to *path*, one JSON object per line.

    Format: ``{"raw": "...", "country_code": "...", "count": N}``. The file is
    only written when there is at least one unmapped value. Returns the total
    number of unmapped occurrences (0 if nothing was written).
    """
    if not _UNMAPPED_LOG:
        return 0
    counter = Counter((e["raw"], e["country_code"]) for e in _UNMAPPED_LOG)
    with open(path, "w", encoding="utf-8") as fh:
        for (raw, cc), count in sorted(counter.items(), key=lambda kv: -kv[1]):
            fh.write(json.dumps({"raw": raw, "country_code": cc, "count": count},
                                ensure_ascii=False) + "\n")
    return len(_UNMAPPED_LOG)


# ── Date parsing ──────────────────────────────────────────────────────────────
# Order matters: DD/MM/YYYY is tried before MM/DD/YYYY so ambiguous LATAM dates
# resolve day-first. FDA dates arrive as YYYYMMDD with no separators.
_DATE_FORMATS = [
    "%d/%m/%Y",               # DD/MM/YYYY (target output + EMA)
    "%Y-%m-%dT%H:%M:%S.%f",   # ISO datetime w/ microseconds (CO Socrata)
    "%Y-%m-%dT%H:%M:%S",      # ISO datetime
    "%Y-%m-%d %H:%M:%S.%f",   # SQL datetime w/ microseconds (ARCSA Fecha_recepcion)
    "%Y-%m-%d %H:%M:%S",      # SQL datetime
    "%Y-%m-%d",               # ISO date
    "%Y%m%d",                 # FDA compact date (e.g. 20230515)
    "%d-%m-%Y",               # DD-MM-YYYY
    "%d/%m/%y",               # DD/MM/YY
    "%m/%d/%Y",               # US format (FDA edge cases)
    "%d/%m/%Y %H:%M:%S",      # DD/MM/YYYY with time
]


def parse_date(raw: Optional[str]) -> Optional[str]:
    """Parse any supported date string to ``DD/MM/YYYY``; ``None`` if unparseable."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Trim a trailing 'Z' (UTC marker) that strptime cannot handle.
    if s.endswith("Z"):
        s = s[:-1]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    # Last resort: dateutil with day-first to stay consistent with LATAM portals.
    if _dateutil_parser is not None:
        try:
            return _dateutil_parser.parse(s, dayfirst=True).strftime("%d/%m/%Y")
        except (ValueError, OverflowError, TypeError):
            pass
    return None


# ── Molecule identity ─────────────────────────────────────────────────────────
def _canonical_molecule(term: str) -> str:
    """Collapse a source-specific molecule term onto the panel's canonical INN.

    Every source labels rows in its own vocabulary — LATAM portals search
    "DAPAGLIFLOZINA" while EMA/FDA use "DAPAGLIFLOZIN" — which split one molecule
    across two rows of the molecule x country matrix and fragmented the competitive
    picture. Canonicalizing here means all 14 extractors keep tagging rows however
    their source spells it, and the canonical schema still carries one identity.

    ``config`` is imported lazily: it imports this module for CANONICAL_FIELDS, so a
    module-level import would be circular. An unrecognized term (an ad-hoc
    ``--molecule`` search) is returned unchanged rather than dropped.
    """
    try:
        import config
        return config.canonical_inn(term) or term
    except Exception:  # pragma: no cover - keeps normalize stdlib-safe in isolation
        return term


# ── Row normalization ─────────────────────────────────────────────────────────
def normalize_row(
    raw: dict,
    *,
    country_code: Optional[str] = None,
    record_type: Optional[str] = None,
    molecule_search_term: Optional[str] = None,
    source_url: Optional[str] = None,
) -> Optional[dict]:
    """Convert one raw extractor dict into a canonical 19-field row.

    Returns ``None`` when ``registration_number`` is absent — the caller drops it.
    Values present in *raw* for country_code / record_type / molecule_search_term /
    source_url take precedence over the keyword defaults.
    """
    reg_num = _clean(raw.get("registration_number"))
    if not reg_num:
        return None  # PK violation — drop row

    cc = (_clean(raw.get("country_code")) or country_code or "")
    cc = cc.upper()
    rt = (_clean(raw.get("record_type")) or record_type or "")
    rt = rt.upper() if rt else None
    mst = (_clean(raw.get("molecule_search_term")) or molecule_search_term or "")
    mst = _canonical_molecule(mst.upper()) if mst else None
    su = _clean(raw.get("source_url")) or source_url or None

    canonical = {
        "registration_number": reg_num,
        "country_code": cc or None,
        "health_authority": HA_MAP.get(cc),
        "record_type": rt,
        "product_name": _clean(raw.get("product_name")),
        "api": _upper(raw.get("api")),
        "concentration": _clean(raw.get("concentration")),
        "dosage_form": _clean(raw.get("dosage_form")),
        "applicant": _clean(raw.get("applicant")),
        "manufacturer": _clean(raw.get("manufacturer")),
        "manufacturer_country": _clean(raw.get("manufacturer_country")),
        "status": normalize_status(raw.get("status"), cc),
        "process_type": _clean(raw.get("process_type")),
        "submission_date": parse_date(raw.get("submission_date")),
        "approval_date": parse_date(raw.get("approval_date")),
        "expiration_date": parse_date(raw.get("expiration_date")),
        "molecule_search_term": mst,
        "source_url": su,
        "extraction_date": date.today().strftime("%d/%m/%Y"),
    }

    # Guarantee every canonical field exists (defensive — all are set above).
    for field in CANONICAL_FIELDS:
        canonical.setdefault(field, None)

    # Carry an optional indication hint for post-filtering. It is NOT a canonical
    # field: CSV writers use fieldnames=CANONICAL_FIELDS with extrasaction="ignore",
    # so this never reaches the output file.
    hint = _clean(raw.get("_indication_hint"))
    if hint:
        canonical["_indication_hint"] = hint
    return canonical


def normalize_rows(raw_rows: list[dict], **kwargs) -> list[dict]:
    """Normalize a list of raw dicts, dropping rows that fail PK enforcement."""
    out: list[dict] = []
    for raw in raw_rows or []:
        row = normalize_row(raw, **kwargs)
        if row is not None:
            out.append(row)
    return out


# ── Deduplication ─────────────────────────────────────────────────────────────
def deduplicate(rows: list[dict]) -> list[dict]:
    """Deduplicate on (registration_number, country_code, record_type).

    Keeps the row with the most recent ``extraction_date``.
    """
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (
            row.get("registration_number", ""),
            row.get("country_code", ""),
            row.get("record_type", ""),
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = row
            continue
        existing_date = _parse_dd_mm_yyyy(existing.get("extraction_date"))
        new_date = _parse_dd_mm_yyyy(row.get("extraction_date"))
        if new_date and (existing_date is None or new_date >= existing_date):
            seen[key] = row
    return list(seen.values())


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean(val) -> Optional[str]:
    """Strip whitespace; collapse empty/placeholder values to None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # Reject pure placeholders that some portals emit instead of blanks.
    if s.upper() in {"N/A", "NA", "-", "--", "ND", "NULL", "NONE", "."}:
        return None
    return s


def _upper(val) -> Optional[str]:
    cleaned = _clean(val)
    return cleaned.upper() if cleaned else None


def _parse_dd_mm_yyyy(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return datetime.strptime(str(val), "%d/%m/%Y").date()
    except ValueError:
        return None
