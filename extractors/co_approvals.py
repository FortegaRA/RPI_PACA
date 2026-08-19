"""
co_approvals.py — Colombia INVIMA approvals via the Socrata OData REST API.

Method: HTTP GET. No browser.
  GET https://www.datos.gov.co/resource/i7cb-raxc.json
      ?$where=upper(principioactivo) like 'REGORAFENIB%'&$limit=1000

The dataset returns one row per CUM (product presentation), and a single
registro sanitario may appear several times with different roles (TITULAR,
FABRICANTE, IMPORTADOR). Rows are grouped on (registrosanitario, principioactivo);
the manufacturer is taken from the FABRICANTE role row.
"""

from __future__ import annotations

import re

import config

COUNTRY_CODE = "CO"
RECORD_TYPE = "APPROVAL"


_PAGE = 1000  # Socrata page size; we paginate so a common molecule is never truncated.

_US_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _iso_from_us_date(raw):
    """Convert Socrata's fechaexpedicion/fechavencimiento to unambiguous ISO.

    i7cb-raxc returns these two dates in US month-first order — confirmed live via
    values whose second component exceeds 12 (e.g. "07/18/2025", "12/30/2025").
    Every other date in this pipeline is LATAM day-first, and normalize.py's parser
    tries day-first first, so left as MM/DD/YYYY these were silently misread
    whenever both components were <=12 (e.g. "06/09/2026" — 9 June — read as 6
    September). Converting to ISO here removes the ambiguity before normalize sees it.
    """
    m = _US_DATE.match(str(raw or "").strip())
    if not m:
        return raw
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{mm}-{dd}"


def _fetch_term(session, base_url: str, term: str, errors: list) -> list[dict]:
    """Fetch every CUM row whose principioactivo CONTAINS the term.

    The match is a substring (``like '%TERM%'``) — NOT a leading anchor — so a
    registration where the INN is preceded by its salt ("TOSILATO DE SORAFENIB"),
    appears in a combination ("METFORMINA + DAPAGLIFLOZINA"), or is buried in a
    free-text formulation ("CADA TABLETA CONTIENE DAPAGLIFLOZINA…") is still found,
    matching what a manual reviewer sees. Results are paginated so a high-volume
    molecule is never silently cut at the page size.
    """
    where = f"upper(principioactivo) like '%{term.upper()}%'"
    out: list[dict] = []
    offset = 0
    while True:
        params = {"$where": where, "$limit": _PAGE, "$offset": offset}
        try:
            resp = session.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            page = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"    [CO-APR] request error for {term}: {exc}")
            errors.append(f"CO-APR {term}: {exc}")
            return out
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        if len(page) < _PAGE:
            break
        offset += _PAGE
    return out


def _dataset_is_empty(session, base_url: str) -> bool:
    """True when the whole CUM dataset holds no rows (an upstream publishing failure).

    Socrata answers a query against an empty dataset with ``HTTP 200`` and ``[]`` —
    indistinguishable, at the query level, from "this molecule has no registration".
    That difference matters: an empty result must never be reported as "no competitor
    product is registered in Colombia" when the truth is that nobody can see the data.

    Observed live on 18/08/2026: INVIMA republished the CUM datasets and every one of
    them (vigentes, vencidos, renovación, otros estados) returned 0 rows, while
    unrelated datasets on datos.gov.co responded normally.
    """
    try:
        resp = session.get(base_url, params={"$select": "count(1) as c"}, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        return bool(payload) and str(payload[0].get("c", "")).strip() == "0"
    except Exception:  # noqa: BLE001 - inconclusive: let the normal path decide
        return False


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    errors = config_dict.setdefault("partial_errors", [])
    session = config_dict.get("session") or config.build_session()
    base_url = config.SOURCE_URLS["co_approvals"]

    if _dataset_is_empty(session, base_url):
        msg = ("CO-APR: el dataset CUM de datos.gov.co está vacío (0 filas en total) — "
               "fallo de publicación en la fuente, NO significa que no haya registros")
        print(f"    [CO-APR] {msg}")
        errors.append(msg)
        return []

    # group key -> {representative row, manufacturer, search_term}
    groups: dict[tuple, dict] = {}
    for m in molecules:
        canon = m["latam_term"].upper()  # tag rows with the canonical term
        for term in config.search_terms(m):  # latam_term + INN-variant aliases
            for raw in _fetch_term(session, base_url, term, errors):
                reg = (raw.get("registrosanitario") or "").strip()
                pa = (raw.get("principioactivo") or "").strip()
                if not reg:
                    continue
                key = (reg, pa)
                entry = groups.setdefault(key, {"rep": raw, "manufacturer": None,
                                                "search_term": canon})
                # Prefer the FABRICANTE row's name as manufacturer.
                if str(raw.get("tiporol", "")).strip().upper() == "FABRICANTE":
                    entry["manufacturer"] = raw.get("nombrerol")
                # Keep a representative row with the most populated product fields.
                if not entry["rep"].get("producto") and raw.get("producto"):
                    entry["rep"] = raw

    rows: list[dict] = []
    for (reg, pa), entry in groups.items():
        rep = entry["rep"]
        rows.append({
            "registration_number": reg,
            "product_name": rep.get("producto"),
            "api": pa or rep.get("principioactivo"),
            "concentration": rep.get("concentracion"),
            "dosage_form": rep.get("formafarmaceutica"),
            "applicant": rep.get("titular"),
            "manufacturer": entry["manufacturer"],
            "status": rep.get("estadoregistro"),
            "approval_date": _iso_from_us_date(rep.get("fechaexpedicion")),
            "expiration_date": _iso_from_us_date(rep.get("fechavencimiento")),
            "country_code": COUNTRY_CODE,
            "record_type": RECORD_TYPE,
            "molecule_search_term": entry["search_term"].upper(),
            "source_url": base_url,
            # ATC description discriminates indication (e.g. tadalafil PAH vs ED).
            "_indication_hint": rep.get("descripcionatc") or rep.get("atc"),
        })

    print(f"    [CO-APR] {len(rows)} unique registrations after dedup")
    return rows
