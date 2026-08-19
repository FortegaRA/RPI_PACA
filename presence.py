"""
presence.py — "we searched, found nothing" rows for novel molecules.

molecules.md flags a few molecules (gene therapy / first-in-class) that are
expected to have ~0 registrations in LATAM, and says: *do not drop — record a
NULL-filled row for countries with no data*. This module synthesizes those rows
so a per-molecule × per-country report shows the molecule was actually checked,
rather than being silently absent.

Rules:
    * Only molecules flagged ``track_if_absent`` get presence rows.
    * A presence row is emitted for a (molecule, country) pair ONLY when that
      country was searched SUCCESSFULLY and returned no real record. A country
      whose extractor errored is skipped — we cannot claim "no data" if we never
      managed to look.
    * The sentinel uses record_type ``NO_DATA`` and a synthetic, clearly-labelled
      registration_number so it satisfies the PK rule and is trivially filtered
      out by consumers, and never counted as an approval or submission.
"""

from __future__ import annotations

from datetime import date

import config
from normalize import CANONICAL_FIELDS, HA_MAP

NO_DATA = "NO_DATA"
_REAL_TYPES = {"APPROVAL", "SUBMISSION", "CANCELLATION"}


def _presence_row(term: str, country_code: str, today: str) -> dict:
    row = {f: None for f in CANONICAL_FIELDS}
    row.update({
        "registration_number": f"NO-DATA-{country_code}-{term}".replace(" ", "_"),
        "country_code": country_code,
        "health_authority": HA_MAP.get(country_code),
        "record_type": NO_DATA,
        "molecule_search_term": term,
        "source_url": (config.COUNTRY_META.get(country_code) or {}).get("source_url"),
        "extraction_date": today,
    })
    return row


def generate_presence_rows(rows: list[dict], molecules: list[dict],
                           country_codes) -> list[dict]:
    """Return presence rows for flagged molecules absent in *country_codes*.

    *rows* are the real canonical rows gathered so far; *country_codes* is the set
    of country codes that were searched successfully (OK / EMPTY / PARTIAL).
    """
    if not getattr(config, "EMIT_PRESENCE_ROWS", True):
        return []
    flagged = [m for m in molecules if m.get("track_if_absent")]
    country_codes = sorted({c for c in (country_codes or set()) if c})
    if not flagged or not country_codes:
        return []

    present: set[tuple] = set()
    for r in rows:
        if (r.get("record_type") or "") in _REAL_TYPES:
            present.add(((r.get("molecule_search_term") or "").upper(),
                         r.get("country_code")))

    today = date.today().strftime("%d/%m/%Y")
    out: list[dict] = []
    for m in flagged:
        term = m["latam_term"].upper()
        for cc in country_codes:
            if (term, cc) not in present:
                out.append(_presence_row(term, cc, today))
    return out
