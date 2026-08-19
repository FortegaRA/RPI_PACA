"""
fda.py — U.S. FDA OpenFDA drugsfda endpoint (reference / forecast source).

Method: HTTP GET, one request per molecule. No browser.
  GET https://api.fda.gov/drug/drugsfda.json?search=active_ingredients.name:{INN}&limit=100

Status is derived from the submissions array: the most recent submission whose
``submission_status`` is one of AP/TA/RF/WD/PR drives the canonical status and,
for AP, the approval date.
"""

from __future__ import annotations

import config

COUNTRY_CODE = "US"

# FDA submission_status -> (raw status string normalize.py understands, is_approval)
_STATUS_CODES = {
    "AP": ("AP", True),    # Approved
    "TA": ("TA", False),   # Tentatively Approved -> PENDING
    "PR": ("PR", False),   # Pending Review -> PENDING
    "RF": ("RF", False),   # Refuse to File -> REJECTED
    "WD": ("WD", False),   # Withdrawn -> CANCELED
}


def _latest_relevant_submission(submissions: list[dict]):
    """Return the most recent submission with a recognized status code."""
    candidates = [s for s in submissions
                  if str(s.get("submission_status", "")).upper() in _STATUS_CODES]
    if not candidates:
        return None
    # submission_status_date is YYYYMMDD; lexical sort == chronological.
    candidates.sort(key=lambda s: str(s.get("submission_status_date", "")), reverse=True)
    return candidates[0]


def _join(parts) -> str | None:
    """Join non-empty ingredient fields with ' + ' (preserves combo composition)."""
    vals = [str(p).strip() for p in parts if p and str(p).strip()]
    return " + ".join(vals) if vals else None


def _map_result(result: dict, search_term: str) -> list[dict]:
    """Map one drugsfda application to ONE row per product (presentation).

    A single application routinely carries multiple products (strengths/forms) and
    each product multiple active ingredients (combinations). The previous code kept
    only ``products[0]``/``ingredients[0]``, collapsing combos and dropping sibling
    presentations — exactly the undercount manual review flags. We now emit one row
    per product, combine all of its active ingredients into ``api``, and make the PK
    unique per presentation (``{app_no}-{product_number}`` when >1 product).
    """
    app_no = result.get("application_number")
    if not app_no:
        return []

    submissions = result.get("submissions") or []
    latest = _latest_relevant_submission(submissions)

    status_raw = None
    approval_date = None
    submission_date = None
    process_type = None
    is_approval = False

    if latest is not None:
        code = str(latest.get("submission_status", "")).upper()
        status_raw, is_approval = _STATUS_CODES.get(code, (None, False))
        date_val = latest.get("submission_status_date")
        if is_approval:
            approval_date = date_val
        else:
            submission_date = date_val
    if submissions:
        process_type = submissions[-1].get("submission_type")

    products = result.get("products") or [{}]
    multi = len(products) > 1
    rows: list[dict] = []
    for product in products:
        ingredients = product.get("active_ingredients") or []
        prod_no = str(product.get("product_number") or "").strip()
        reg_num = f"{app_no}-{prod_no}" if (multi and prod_no) else app_no
        rows.append({
            "registration_number": reg_num,
            "product_name": product.get("brand_name"),
            "api": _join(i.get("name") for i in ingredients),
            "concentration": _join(i.get("strength") for i in ingredients),
            "dosage_form": product.get("dosage_form"),
            "applicant": result.get("sponsor_name"),
            "status": status_raw,
            "process_type": process_type,
            "submission_date": submission_date,
            "approval_date": approval_date,
            "country_code": COUNTRY_CODE,
            "record_type": "APPROVAL" if is_approval else "SUBMISSION",
            "molecule_search_term": search_term.upper(),
            "source_url": config.SOURCE_URLS["fda"],
        })
    return rows


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    session = config_dict.get("session") or config.build_session()
    api_key = config_dict.get("fda_api_key")
    base_url = config.SOURCE_URLS["fda"]
    rows: list[dict] = []

    errors = config_dict.setdefault("partial_errors", [])
    for m in molecules:
        term = m["fda_term"]
        results = _query_term(session, base_url, term, api_key, errors)
        for result in results:
            rows.extend(_map_result(result, term))

    print(f"    [FDA] collected {len(rows)} rows")
    return rows


def _query_term(session, base_url: str, term: str, api_key, errors: list) -> list[dict]:
    """Query drugsfda by active ingredient, falling back to generic name.

    Note: the searchable field is ``products.active_ingredients.name`` — the
    un-nested ``active_ingredients.name`` path returns HTTP 404.
    """
    for field in ("products.active_ingredients.name", "openfda.generic_name"):
        params = {"search": f'{field}:"{term}"', "limit": 100}
        if api_key:
            params["api_key"] = api_key
        try:
            resp = session.get(base_url, params=params, timeout=10)
        except Exception as exc:  # noqa: BLE001
            print(f"    [FDA] request error for {term}: {exc}")
            errors.append(f"FDA {term}: {exc}")
            return []
        if resp.status_code == 404:
            continue  # no matches on this field — try the next
        if resp.status_code != 200:
            print(f"    [FDA] HTTP {resp.status_code} for {term}")
            errors.append(f"FDA {term}: HTTP {resp.status_code}")
            return []
        try:
            results = resp.json().get("results", [])
        except ValueError:
            return []
        if results:
            return results
    return []
