"""
sv.py — El Salvador SRS approvals.

The public search at /productos/buscarProducto is backed by a DataTables
server-side JSON endpoint (confirmed live):

    GET https://expedientes.srs.gob.sv/productos/lista
        ?draw=1&start=0&length=100&filtro=principio_activo&busqueda={TERM}

Hitting that endpoint directly with ``requests`` is far more reliable than driving
the browser (no ChromeDriver, no DataTables timing), so this extractor needs **no
Selenium**. The ``filtro=principio_activo`` parameter performs the active-ingredient
search server-side; pagination is via start/length until recordsFiltered is reached.

Field mapping (JSON record):
    registroSanitario   -> registration_number
    nombreRegistro      -> product_name
    titular             -> applicant
    estado              -> status (ACTIVO -> APPROVED, etc.)
    primeraAutorizacion -> approval_date (YYYY-MM-DD)
    api / dosage_form / concentration -> None (not exposed by this endpoint)
"""

from __future__ import annotations

import config

COUNTRY_CODE = "SV"
BASE = "https://expedientes.srs.gob.sv"
SEARCH_PAGE = f"{BASE}/productos/buscarProducto"
LIST_URL = f"{BASE}/productos/lista"
SOURCE_URL = config.SOURCE_URLS["sv"]
PAGE_SIZE = 100
MAX_PAGES = 30  # safety cap (3,000 rows/molecule)


def _fetch_page(session, term: str, start: int) -> dict | None:
    params = {
        "draw": 1,
        "start": start,
        "length": PAGE_SIZE,
        "filtro": "principio_activo",
        "busqueda": term,
    }
    resp = session.get(LIST_URL, params=params, timeout=30,
                       headers={"X-Requested-With": "XMLHttpRequest"})
    resp.raise_for_status()
    return resp.json()


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    errors = config_dict.setdefault("partial_errors", [])
    session = config_dict.get("session") or config.build_session()

    # Prime cookies / session on the search page.
    try:
        session.get(SEARCH_PAGE, timeout=25)
    except Exception as exc:  # noqa: BLE001
        print(f"    [SV] search-page priming failed: {exc}")
        errors.append(f"SV: priming failed: {exc}")

    rows: list[dict] = []
    # First molecule to claim a registration keeps it. The panel deliberately holds
    # both specific molecules and a broader class entry (Factor VIII), and the class
    # sits last precisely so it only picks up what the specific ones left. Without
    # this guard the same product comes back under several queries and deduplication
    # keeps whichever was appended last — handing ESPEROCT to the class entry instead
    # of to turoctocog alfa pegol.
    claimed: set = set()
    for m in molecules:
        canon = m["latam_term"].upper()  # tag rows with the canonical term
        for term in config.search_terms(m):  # latam_term + INN-variant aliases
            try:
                start = 0
                for _ in range(MAX_PAGES):
                    payload = _fetch_page(session, term, start)
                    data = (payload or {}).get("data") or []
                    if not data:
                        break
                    for rec in data:
                        reg = rec.get("registroSanitario")
                        if reg in claimed:
                            continue
                        claimed.add(reg)
                        rows.append({
                            "registration_number": reg,
                            "product_name": rec.get("nombreRegistro"),
                            "applicant": rec.get("titular"),
                            "status": rec.get("estado"),
                            "approval_date": rec.get("primeraAutorizacion"),
                            "country_code": COUNTRY_CODE,
                            "record_type": "APPROVAL",
                            "molecule_search_term": canon,
                            "source_url": SOURCE_URL,
                            "_indication_hint": (rec.get("indicacionesTerapeuticas")
                                                 or rec.get("clasificacion")
                                                 or rec.get("categoria")),
                        })
                    total = (payload or {}).get("recordsFiltered", 0)
                    start += PAGE_SIZE
                    if start >= total:
                        break
            except Exception as exc:  # noqa: BLE001
                print(f"    [SV] error for {term}: {exc}")
                errors.append(f"SV {term}: {exc}")
                continue

    print(f"    [SV] collected {len(rows)} rows")
    return rows
