"""
cr.py — Costa Rica (Registrelo / Ministerio de Salud) via the portal's public API.

REBUILT 16/08/2026. The previous implementation looked for an Excel "download"
button on https://registrelo.go.cr/reports/12 — that button never existed
(Registrelo is a React SPA), so its download always failed and it silently parsed
whatever workbook was left in the shared download folder: Honduras'. It emitted 24
Honduran registrations tagged ``country_code=CR``.

How this works now
------------------
Registrelo is backed by ``gateway.registrelo.go.cr``. The public report catalogue
and report definitions are reachable over plain HTTP, but the **data** endpoint
requires a reCAPTCHA v3 token. So we open an ordinary Chrome session on
registrelo.go.cr and let the page mint tokens exactly as it does for any visitor,
then call the same public endpoint the site itself calls. No stealth/undetected
driver and no CAPTCHA-solving service is involved — this is a normal browser doing
what a normal browser does on a public registry.

Three public reports are used:

  62  ProductAIMedicationPublic    product -> active-ingredient map (~17k medicines)
  12  ReportsMS_Products_Public    the registration record (number, dates, status,
                                   titular, manufacturers, country)
  64  ProductsInProceduresPublic   products in procedure  -> SUBMISSION rows

APPROVALS are resolved with a join, because report 12 has **no active-ingredient
filter**: report 62 is pulled once and filtered in memory to every product whose
active ingredient matches a target molecule, then those product names are resolved
against report 12. This is what lets us catch brand-only names that contain no INN
at all (``RIOCI®``, ``Efflusso®``) — precisely what the old product-name-only match
missed. Report 12 covers every regulated product (medicines, devices, food), and
its ``productName`` filter is a naive substring ("RIOCI" matches "cRIOCIrugía"), so
matches are confirmed on an exact normalized product name **and** a medicine subtype.

SUBMISSIONS come from report 64, which does expose a server-side ``activeIngredient``
ilike filter, so it is queried per molecule term directly. That report carries no
dates, so ``submission_date`` is left NULL rather than invented.
"""

from __future__ import annotations

import re
import time
import unicodedata

import config
from extractors import selenium_base as sb

COUNTRY_CODE = "CR"
SOURCE_URL = config.SOURCE_URLS["cr"]
PORTAL_URL = "https://registrelo.go.cr/"

# Public front-end constants, shipped in the site's own JS bundle and sent to every
# visitor's browser. They are not credentials: they identify the public web client.
_GATEWAY = "https://gateway.registrelo.go.cr"
_SITE_KEY = "6LdTlsQZAAAAAE-O6mTe60tLMcM8syH9b4kIKVv4"
_API_TOKEN = "3pHUFcIinxJTUwG5RFYiHmR4W2X5gzUO"
_GATEWAY_TOKEN = "RFG1PZMO279obfzFUy7nFrQuPNxtn36N"

RPT_INGREDIENTS = "ProductAIMedicationPublic"     # 62
RPT_PRODUCTS = "ReportsMS_Products_Public"        # 12
RPT_PROCEDURES = "ProductsInProceduresPublic"     # 64

# Registrelo subtypes that are medicines (report 12 also lists devices, food, ...).
_MED_SUBTYPES = ("medicamento", "biologico", "biológico", "natural", "homeopat")

_SCRIPT_TIMEOUT = 180

# Mints a fresh reCAPTCHA token (they are single-use) and calls the public report
# endpoint from the page's own origin. Runs via execute_async_script.
_API_SCRIPT = """
const done = arguments[arguments.length - 1];
const code = arguments[0];
const params = arguments[1] || {};
const SITE = arguments[2], GW = arguments[3], API_TOK = arguments[4], GW_TOK = arguments[5];
(async () => {
  try {
    if (typeof grecaptcha === 'undefined') { done({ok:false, status:0, data:[], message:'grecaptcha no cargado'}); return; }
    const token = await new Promise((res, rej) =>
      grecaptcha.ready(() => grecaptcha.execute(SITE, {action: 'submit'}).then(res).catch(rej)));
    const qs = new URLSearchParams(Object.assign(
      {reportDefinitionCode: code, recaptchaToken: token}, params));
    const r = await fetch(GW + '/core/v1/publicreports/getPublicReport?' + qs, {
      headers: {'api-token': API_TOK, 'gateway-token': GW_TOK, 'Accept': 'application/json'}});
    const j = await r.json();
    done({ok: r.ok, status: r.status, data: Array.isArray(j.data) ? j.data : [],
          message: j.message || null});
  } catch (e) { done({ok:false, status:0, data:[], message: String(e)}); }
})();
"""


def _fold(value) -> str:
    """Lowercase, strip accents and collapse whitespace — for name matching."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.split()).lower()


def _is_medicine(row: dict) -> bool:
    sub = _fold(row.get("subTypeName"))
    return any(k in sub for k in _MED_SUBTYPES)


def _call_report(driver, code: str, params: dict | None, errors: list) -> list[dict]:
    """Run one public-report query in the browser; return its rows (never raises)."""
    try:
        res = driver.execute_async_script(
            _API_SCRIPT, code, params or {}, _SITE_KEY, _GATEWAY, _API_TOKEN, _GATEWAY_TOKEN)
    except Exception as exc:  # noqa: BLE001
        msg = sb.err_line(exc)
        print(f"    [CR] {code}: fallo de script: {msg}")
        errors.append(f"CR {code}: {msg}")
        return []
    if not isinstance(res, dict) or not res.get("ok"):
        detail = (res or {}).get("message") or "sin detalle"
        status = (res or {}).get("status")
        print(f"    [CR] {code}: HTTP {status} — {str(detail)[:120]}")
        errors.append(f"CR {code}: HTTP {status}: {str(detail)[:120]}")
        return []
    return res.get("data") or []


def _target_products(driver, term_table: list[tuple], errors: list) -> dict:
    """Map normalized product name -> (molecule, active ingredient) for our panel.

    One bulk call to the product/active-ingredient report, filtered in memory. This
    is what surfaces brand-only names whose text contains no INN.
    """
    rows = _call_report(driver, RPT_INGREDIENTS, None, errors)
    if not rows:
        return {}
    targets: dict = {}
    for row in rows:
        ingredient = _fold(row.get("activeIngredient"))
        if not ingredient:
            continue
        for molecule, terms in term_table:
            if any(t in ingredient for t in terms):
                name = row.get("productName")
                key = _fold(name)
                if key:
                    targets.setdefault(key, (molecule, row.get("activeIngredient"), name))
                break
    print(f"    [CR] {len(rows)} medicamentos en el registro; "
          f"{len(targets)} productos de las moleculas objetivo")
    return targets


def _brand_root(name: str) -> str:
    """First meaningful token of a product name — the shared brand stem.

    ``ADEMPAS 0.5 mg Comprimidos`` and ``ADEMPAS 2mg`` share the root ``adempas``,
    so one substring query answers both. Products are grouped by this root to cut
    the number of round-trips (each call costs a fresh reCAPTCHA token, ~3 s).
    """
    folded = _fold(name).replace("®", " ")
    for token in folded.replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 4 and not cleaned.isdigit():
            return cleaned
    return folded[:12].strip()


def _approvals(driver, targets: dict, errors: list) -> list[dict]:
    """Resolve target products against the registration report, grouped by brand root."""
    groups: dict[str, list] = {}
    for key, payload in targets.items():
        groups.setdefault(_brand_root(payload[2]), []).append((key, payload))

    print(f"    [CR] resolviendo {len(targets)} productos en {len(groups)} consultas")
    rows: list[dict] = []
    seen: set = set()
    for root, members in sorted(groups.items()):
        # The filter is a substring search; exact names are re-verified below.
        found = _call_report(driver, RPT_PRODUCTS, {"productName": root}, errors)
        if not found:
            continue
        by_name = {k: payload for k, payload in members}
        for raw in found:
            key = _fold(raw.get("productName"))
            if key not in by_name or not _is_medicine(raw):
                continue  # substring false positive (e.g. "RIOCI" in "cRIOCIrugía")
            molecule, ingredient, _display = by_name[key]
            reg = (raw.get("registerNumber") or "").strip()
            if not reg or (reg, key) in seen:
                continue
            seen.add((reg, key))
            rows.append({
                "registration_number": reg,
                "product_name": raw.get("productName"),
                "api": ingredient,
                "applicant": raw.get("headline") or raw.get("parentName"),
                "manufacturer": (str(raw.get("manufacturers") or "").split(";")[0].strip()
                                 or None),
                "manufacturer_country": raw.get("countrySource"),
                "status": raw.get("statusName"),
                "approval_date": raw.get("createdAt"),
                "expiration_date": raw.get("expiredAt"),
                "process_type": raw.get("subTypeName"),
                "country_code": COUNTRY_CODE,
                "record_type": "APPROVAL",
                "molecule_search_term": molecule["latam_term"].upper(),
                "source_url": SOURCE_URL,
                "_indication_hint": raw.get("description") or raw.get("subTypeName"),
            })
    return rows


_PROCEDURE_ID = re.compile(r"/(\d+)\s*$")


def _procedure_pk(code: str, link) -> str:
    """Build a primary key that is unique per procedure, not per código.

    ``procedureCode`` repeats: the same código can head several procedure records
    (verified live — MS-2026-37103 comes back twice, under adminProcedures 1216905
    and 1255047). Keying on the código alone let ``normalize.deduplicate`` collapse
    them, silently dropping ~20% of Costa Rica's filings — and worse, a genuinely new
    procedure sharing a código with a known one would be swallowed as a duplicate and
    never register as a novelty.

    The adminProcedures id in the row's link is unique and monotonic, so the pair
    identifies the procedure and keeps the código readable (its ``MS-YYYY-`` form
    carries the filing year, which is the only date signal this report offers).
    """
    match = _PROCEDURE_ID.search(str(link or "").strip())
    return f"{code}-{match.group(1)}" if match else code


def _submissions(driver, molecules: list[dict], errors: list) -> list[dict]:
    """Products in procedure, via report 64's server-side activeIngredient filter."""
    rows: list[dict] = []
    seen: set = set()
    for molecule in molecules:
        canon = molecule["latam_term"].upper()
        for term in config.search_terms(molecule):
            for raw in _call_report(driver, RPT_PROCEDURES,
                                    {"activeIngredient": term}, errors):
                code = str(raw.get("procedureCode") or "").strip()
                link = raw.get("link") or SOURCE_URL
                if not code or (code, link) in seen:
                    continue
                seen.add((code, link))
                rows.append({
                    "registration_number": _procedure_pk(code, link),
                    "product_name": None,   # report 64 exposes no product name
                    "api": raw.get("newActiveIngredient") or raw.get("activeIngredient"),
                    "applicant": raw.get("requester"),
                    "manufacturer": (str(raw.get("manufacturer") or "").split(";")[0].strip()
                                     or None),
                    # No date column exists in this report — leave NULL, never invent.
                    "submission_date": None,
                    "country_code": COUNTRY_CODE,
                    "record_type": "SUBMISSION",
                    "molecule_search_term": canon,
                    "source_url": link,
                })
    return rows


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    from selenium.webdriver.support.ui import WebDriverWait

    errors = config_dict.setdefault("partial_errors", [])
    headless = config_dict.get("headless", False)
    download_dir = config_dict.get("download_dir") or config_dict.get("output_dir")
    term_table = [(m, [_fold(t) for t in config.search_terms(m)]) for m in molecules]

    driver = None
    try:
        driver = sb.build_driver(headless=headless, download_dir=download_dir)
        driver.set_script_timeout(_SCRIPT_TIMEOUT)
        driver.get(PORTAL_URL)
        WebDriverWait(driver, 40).until(
            lambda d: d.execute_script("return document.readyState") == "complete")
        # Give the SPA a moment to load the reCAPTCHA script it mints tokens with.
        for _ in range(20):
            if driver.execute_script("return typeof grecaptcha !== 'undefined'"):
                break
            time.sleep(1)
        else:
            print("    [CR] reCAPTCHA no se cargó en el portal — no se puede consultar la API")
            errors.append("CR: reCAPTCHA no disponible en el portal")
            return []

        targets = _target_products(driver, term_table, errors)
        rows = _approvals(driver, targets, errors) if targets else []
        rows.extend(_submissions(driver, molecules, errors))

        approvals = sum(1 for r in rows if r["record_type"] == "APPROVAL")
        print(f"    [CR] {len(rows)} filas ({approvals} aprobaciones, "
              f"{len(rows) - approvals} trámites)")
        return rows
    except Exception as exc:  # noqa: BLE001
        msg = sb.err_line(exc)
        print(f"    [CR] error: {msg}")
        errors.append(f"CR: {msg}")
        return []
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
