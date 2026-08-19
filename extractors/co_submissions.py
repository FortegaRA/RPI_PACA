"""
co_submissions.py — Colombia INVIMA submissions (trámites radicados) via Socrata.

Method: HTTP GET (Socrata OData REST). NO Selenium.

The radicados dataset (datos.gov.co ``t2gj-yg8s``) lists every trámite filed with
the Dirección de Medicamentos, but has NO active-ingredient column. So we filter to
the target molecules by joining on ``expediente`` with the approvals dataset
(``i7cb-raxc``), which carries ``principioactivo`` + ``producto`` + ``titular``:

    1. For each molecule, read its expedientes from the approvals dataset.
    2. Pull every radicado for those expedientes from the radicados dataset.
    3. Emit one SUBMISSION row per radicado, enriched with the molecule/product
       from the join.

IMPORTANT — this is the HISTORICAL archive (data through ~2024-07), NOT a live
"last 60 days" view, and it misses first-time submissions whose product is not yet
in the approvals registry. For real-time radicados the TransparenciaWeb PrimeFaces
portal would be needed (not implemented — see project notes).

    radicado              -> registration_number (PK)
    fecha_inicio_tramite  -> submission_date
    tramite               -> process_type
    estado_tramite        -> status
    (joined) producto     -> product_name
    (joined) principioactivo -> api
    (joined) titular      -> applicant
"""

from __future__ import annotations

import config

COUNTRY_CODE = "CO"
RECORD_TYPE = "SUBMISSION"
APPROVALS_URL = config.SOURCE_URLS["co_approvals"]  # i7cb-raxc (has expediente + api)
RADICADOS_URL = "https://www.datos.gov.co/resource/t2gj-yg8s.json"
_EXP_BATCH = 40  # expedientes per radicados query (keeps the $where URL bounded)


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _fetch_expedientes(session, term: str, errors: list) -> list[dict]:
    params = {
        "$select": "expediente, principioactivo, producto, titular",
        "$where": f"upper(principioactivo) like '{term.upper()}%'",
        "$limit": 2000,
    }
    try:
        resp = session.get(APPROVALS_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        print(f"    [CO-SUB] approvals lookup error for {term}: {exc}")
        errors.append(f"CO-SUB {term}: approvals lookup {exc}")
        return []


def _fetch_radicados(session, where: str, errors: list) -> list[dict]:
    try:
        resp = session.get(RADICADOS_URL, params={"$where": where, "$limit": 5000}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        print(f"    [CO-SUB] radicados query error: {exc}")
        errors.append(f"CO-SUB: radicados query {exc}")
        return []


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    errors = config_dict.setdefault("partial_errors", [])
    session = config_dict.get("session") or config.build_session()

    # 1. expediente -> molecule/product info, from the approvals dataset.
    exp_map: dict[str, dict] = {}
    for m in molecules:
        canon = m["latam_term"].upper()
        for term in config.search_terms(m):
            for raw in _fetch_expedientes(session, term, errors):
                exp = (raw.get("expediente") or "").strip()
                if exp and exp not in exp_map:
                    exp_map[exp] = {
                        "canon": canon,
                        "api": raw.get("principioactivo"),
                        "producto": raw.get("producto"),
                        "titular": raw.get("titular"),
                    }

    if not exp_map:
        print("    [CO-SUB] no expedientes found for target molecules")
        return []

    # 2. Pull every radicado for those expedientes (batched), then map to canonical.
    rows: list[dict] = []
    for batch in _chunks(list(exp_map), _EXP_BATCH):
        where = " OR ".join(f"expediente='{e}'" for e in batch)
        for rad in _fetch_radicados(session, where, errors):
            exp = (rad.get("expediente") or "").strip()
            info = exp_map.get(exp, {})
            rows.append({
                "registration_number": rad.get("radicado"),
                "product_name": info.get("producto"),
                "api": info.get("api"),
                "applicant": info.get("titular"),
                "status": rad.get("estado_tramite"),
                "process_type": rad.get("tramite"),
                "submission_date": rad.get("fecha_inicio_tramite"),
                "country_code": COUNTRY_CODE,
                "record_type": RECORD_TYPE,
                "molecule_search_term": info.get("canon"),
                "source_url": RADICADOS_URL,
            })

    print(f"    [CO-SUB] {len(rows)} trámites across {len(exp_map)} expedientes "
          "(historical archive, not last-60-days)")
    return rows
