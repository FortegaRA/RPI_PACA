"""
ec.py — Ecuador ARCSA (controlsanitario.gob.ec) — bulk report download + in-memory filter.

Method: HTTP GET of the public bulk report, streamed and filtered. NO Selenium, NO
per-molecule rate-limited queries.

ARCSA does NOT expose a per-molecule search — its index search box routes to
``/publico/consultas/reporte/{type}`` (CodeIgniter), and each of those returns the
ENTIRE registry for that report type as one large HTML table (~15k rows, tens of MB)
and IGNORES the query term. So the right model is exactly Honduras': download the
bulk report ONCE per type and filter the rows in memory.

Report types (confirmed 16/06/2026):
    /reporte/1  -> Medicamentos, FULL dump (~15k rows, 42 cols, ~44 MB). Has
                   Principios_activos + Nombre_producto + Fecha_emision/Fecha_vigencia.
                   This is the one we use.
    /reporte/2,3,4 -> filtered/partial views (near-empty without query params).
The ~44 MB response is parsed with a streaming HTMLParser that emits one row at a
time, so only the matching rows are kept (memory stays bounded).
"""

from __future__ import annotations

import html as _html
import re

import config

_TR_OPEN = re.compile(r"<tr[^>]*>", re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    """Strip tags + unescape entities + collapse whitespace from a cell fragment."""
    text = _TAG.sub(" ", fragment)
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()

COUNTRY_CODE = "EC"
SOURCE_URL = config.SOURCE_URLS["ec"]
INDEX_URL = SOURCE_URL
REPORT_URL = "https://aplicaciones.controlsanitario.gob.ec/publico/consultas/reporte/{}"

# The "Descargas" strip on the ARCSA consultas page exposes FOUR separate dumps, each
# a different stage of a registration's life. Labels below are the portal's own:
#
#   1  Registros Sanitarios Vigentes            -> granted, in force      APPROVAL
#   2  Total de Solicitudes Ingresadas          -> filings received       SUBMISSION
#   3  Total Registros Sanitarios Caducados     -> lapsed                 APPROVAL/EXPIRED
#   4  Total Reg. Suspendidos o Cancelados      -> pulled from market     CANCELLATION
#
# Report 2 is the only real filing stream ARCSA publishes; report 1's
# `fecha_recepcion_solicitud` column is NOT an original filing date (verified: not one
# of 161 matched rows had it before its own approval date).
REPORTS = {
    1: {"label": "Vigentes", "record_type": "APPROVAL",
        # This dump carries a `fecha_recepcion_solicitud` column, but it is NOT the
        # date the product was originally filed: across 161 matched rows not one was
        # earlier than that row's own approval date (40% equal it, 60% fall after it),
        # so it tracks the reception of whatever later procedure touched the record.
        # Writing it into `submission_date` put a post-approval date in a field that
        # means "when this was filed" and let approvals leak into the filings view.
        # Real filings come from report 2.
        "no_dates": ("submission_date",)},
    2: {"label": "Solicitudes Ingresadas", "record_type": "SUBMISSION",
        # A filing is identified by its solicitud number; the registration number it
        # references may still be blank or belong to the record being modified.
        "pk": ["numero_solicitud", "numero_registro_sanitario"],
        # "Ingresada" means received and in process — the registry's own `estado`
        # column describes the REGISTRATION ("VIGENTE"), not the filing, so using it
        # here would mark a pending application as approved.
        "status": "PENDING",
        "no_dates": ("approval_date", "expiration_date")},
    3: {"label": "Caducados", "record_type": "APPROVAL"},
    4: {"label": "Suspendidos o Cancelados", "record_type": "CANCELLATION"},
}

# Only the two streams the team tracks: what is in force, and what has been filed.
# Reports 3 and 4 stay described above because knowing they exist matters, but they
# are not pulled; enable them per-run via `ec_report_types` if that ever changes.
DEFAULT_REPORT_TYPES = [1, 2]

# Report column (lowercased <th>) -> canonical raw field.
_COL = {
    "registration_number": ["numero_registro_sanitario"],
    "product_name": ["nombre_producto"],
    "api": ["principios_activos"],
    "concentration": ["concentracion_principio_activo"],
    "dosage_form": ["forma_farmaceutica"],
    "applicant": ["nombre_razon_social_solicitante", "titular_producto"],
    "manufacturer": ["nombre_fabricante"],
    "manufacturer_country": ["pais_fabricante"],
    "status": ["estado", "estado_actual_vue", "estado_detalle_modificacion"],
    "approval_date": ["fecha_emision_registro_sanitario"],
    "expiration_date": ["fecha_vigencia_registro_sanitario"],
    "submission_date": ["fecha_recepcion_solicitud", "fecha_recepcion"],
}


def _parse_rows(html: str):
    """Yield (rows_scanned, row_dict) for each data row of the report table.

    Headers come from the ``<th>`` cells. Rows are sliced between ``<tr>`` START
    tags (not ``<tr>…</tr>``) because the ARCSA report omits the closing ``</tr>``
    — a ``<tr>…</tr>`` regex would swallow every data row into one blob. html.parser
    also desyncs on unescaped characters in the cells, so we use regex on the flat
    grid, which is robust here.
    """
    headers = [_clean(h).lower() for h in _TH.findall(html)]
    if "numero_registro_sanitario" not in headers:
        return  # structure changed
    width = len(headers)
    starts = [m.end() for m in _TR_OPEN.finditer(html)]
    starts.append(len(html))
    scanned = 0
    for i in range(len(starts) - 1):
        cells = _TD.findall(html[starts[i]:starts[i + 1]])
        if len(cells) < 10:  # header row (<th>) / layout rows
            continue
        scanned += 1
        yield scanned, dict(zip(headers, [_clean(c) for c in cells[:width]]))


def _term_table(molecules):
    return [(m, [t.lower() for t in config.search_terms(m)]) for m in molecules]


# ARCSA stores the active ingredient as a free-text formulation blurb in
# Principios_activos, e.g. "CADA TABLETA RECUBIERTA CONTIENE: DAPAGLIFLOZINA
# PROPANEDIOL MONOHIDRATO *** 10,00 MG ....". The strengths already live in the
# concentration column, so for the canonical `api` we extract just the ingredient
# name: drop the "… CONTIENE:" preamble, then cut at the first number / asterisk /
# dot-padding and trim pharmacopoeia qualifiers.
_API_CUT = re.compile(r"[\d*]|\.{3,}")
_API_TAIL = re.compile(r"\b(USP|BP|EP|PH\.?\s*EUR\.?|EQUIVALENTE\s+A?|MICRONIZAD[OA])\b.*$")


def _clean_api(raw, molecule: dict) -> str:
    """Reduce ARCSA's formulation blurb to a clean INN, else the canonical term."""
    canon = molecule["latam_term"].upper()
    if not raw:
        return canon
    s = str(raw).upper()
    if "CONTIENE" in s:
        s = s.split("CONTIENE", 1)[1].lstrip(": ")
    s = _API_CUT.split(s, 1)[0]
    s = _API_TAIL.sub("", s)
    s = " ".join(s.split()).strip(" :,-.")
    # Keep the cleaned name only if it still carries the INN we matched on;
    # otherwise fall back to the canonical term so `api` is never noise.
    terms = [t.upper() for t in config.search_terms(molecule)]
    return s if (s and any(t in s for t in terms)) else canon


def _map_row(rowd: dict, molecule: dict, spec: dict) -> dict:
    def g(*keys):
        for k in keys:
            v = rowd.get(k)
            if v:
                return v
        return None
    row = {
        "registration_number": g(*spec.get("pk", _COL["registration_number"])),
        "product_name": g(*_COL["product_name"]),
        "api": _clean_api(g(*_COL["api"]), molecule),
        "concentration": g(*_COL["concentration"]) or g(*_COL["api"]),
        "dosage_form": g(*_COL["dosage_form"]),
        "applicant": g(*_COL["applicant"]),
        "manufacturer": g(*_COL["manufacturer"]),
        "manufacturer_country": g(*_COL["manufacturer_country"]),
        "status": spec.get("status") or g(*_COL["status"]),
        "approval_date": g(*_COL["approval_date"]),
        "expiration_date": g(*_COL["expiration_date"]),
        "submission_date": g(*_COL["submission_date"]),
        "country_code": COUNTRY_CODE,
        "record_type": spec["record_type"],
        "molecule_search_term": molecule["latam_term"].upper(),
        "source_url": SOURCE_URL,
        "_indication_hint": g("tipo_medicamento", "via_administracion"),
    }
    # A filing has not been granted anything yet, so it carries no approval or
    # expiry date even when the sheet reuses those column names.
    for field in spec.get("no_dates", ()):
        row[field] = None
    return row


def _download_and_filter(session, rtype: int, term_table, errors: list) -> list[dict]:
    spec = REPORTS.get(rtype, {"label": f"reporte {rtype}", "record_type": "APPROVAL"})
    label = spec["label"]
    url = REPORT_URL.format(rtype)
    try:
        resp = session.get(url, timeout=180)
        if resp.status_code != 200:
            print(f"    [EC] {label}: HTTP {resp.status_code}")
            errors.append(f"EC: report {rtype} ({label}) HTTP {resp.status_code}")
            return []
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        print(f"    [EC] {label} download failed: {exc}")
        errors.append(f"EC: report {rtype} ({label}) failed: {exc}")
        return []

    matches: list[dict] = []
    scanned = 0
    for scanned, rowd in _parse_rows(html):
        api = (rowd.get("principios_activos") or "").lower()
        if not api:
            continue
        for molecule, terms in term_table:
            if any(t in api for t in terms):
                matches.append(_map_row(rowd, molecule, spec))
                break

    print(f"    [EC] {label}: scanned {scanned} rows, "
          f"{len(matches)} match target molecules")
    if scanned == 0:
        errors.append(f"EC: report {rtype} ({label}) returned no parseable rows "
                      "(portal structure may have changed)")
    return matches


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    errors = config_dict.setdefault("partial_errors", [])
    session = config_dict.get("session_ec") or config.build_session(headers=config.EC_HEADERS)
    report_types = config_dict.get("ec_report_types", DEFAULT_REPORT_TYPES)

    # Prime cookies on the index page.
    try:
        session.get(INDEX_URL, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"    [EC] index GET failed: {exc}")
        errors.append(f"EC: index GET failed: {exc}")

    term_table = _term_table(molecules)
    rows: list[dict] = []
    for rtype in report_types:
        rows.extend(_download_and_filter(session, rtype, term_table, errors))

    approvals = sum(1 for r in rows if r["record_type"] == "APPROVAL")
    subs = sum(1 for r in rows if r["record_type"] == "SUBMISSION")
    print(f"    [EC] collected {len(rows)} rows ({approvals} aprobaciones, "
          f"{subs} solicitudes) de report(s) {report_types}")
    return rows
