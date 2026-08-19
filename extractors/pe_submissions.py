"""
pe_submissions.py — Peru DIGEMID submissions (Selenium + CDP stealth, Livewire table).

Portal: https://www.digemid.minsa.gob.pe/solicitudesRs/
No Cloudflare challenge here (confirmed: plain GET returns 200), but the search is
the same Livewire form as the approvals portal — no name/id on the active-ingredient
field (found by its "Ejemplo: Paracetamol" placeholder), honey_* honeypots to avoid,
and a submit button ("Realizar Consulta", type=submit) rather than ENTER. The search
plumbing is fixed and submits cleanly.

KNOWN GAP (14/06/2026): this portal renders results as DIV cards, NOT a <table>, so
`_harvest`/`wait_for_table` find nothing (returns a clean EMPTY, not an error). The
results-harvest still needs confirming against the live div structure — until then
submissions reliably returns 0 rows. Approvals (pe_approvals --pe-stealth) is the
fully-working Peru path.

Stealth JS is injected via CDP (selenium_base.build_driver); we wait HONEYPOT_WAIT
after each load before interacting. MAX_PAGES per molecule keeps runtime bounded.

Composite status (raw, normalized later):
  Situación=Atendido + Resultado=Aprobado -> "APROBADO"
  Situación=Atendido + Resultado=Denegado -> "DENEGADO"
  Situación=En trámite                    -> "EN TRAMITE"
  anything else                           -> None
"""

from __future__ import annotations

import time

import config
from extractors import selenium_base as sb

COUNTRY_CODE = "PE"
SOURCE_URL = config.SOURCE_URLS["pe_submissions"]
HONEYPOT_WAIT = 3.5
MAX_PAGES = 3
TABLE_CSS = "table"

# Known column order (positional fallback).
_POS = {
    "registration_number": 0,   # Expediente
    "submission_date": 1,       # Fecha trámite
    "process_type": 2,          # Trámite
    "product_name": 3,          # Nombre Producto
    "concentration": 4,         # Concentración
    "dosage_form": 5,           # Forma Farmacéutica
    "api": 7,                   # Principio Activo
    "applicant": 8,             # Solicitante
    "situacion": 10,            # Situación
    "resultado": 11,            # Resultado
}
_COLS = {
    "registration_number": ["expediente"],
    "submission_date": ["fecha trámite", "fecha tramite"],
    "process_type": ["trámite", "tramite"],
    "product_name": ["nombre producto"],
    "concentration": ["concentración", "concentracion"],
    "dosage_form": ["forma farmacéutica", "forma farmaceutica"],
    "api": ["principio activo"],
    "applicant": ["solicitante"],
    "situacion": ["situación", "situacion"],
    "resultado": ["resultado"],
}


def _composite_status(situacion: str, resultado: str):
    s = (situacion or "").strip().lower()
    r = (resultado or "").strip().lower()
    if s == "atendido" and r == "aprobado":
        return "APROBADO"
    if s == "atendido" and r == "denegado":
        return "DENEGADO"
    if s.startswith("en trámite") or s.startswith("en tramite"):
        return "EN TRAMITE"
    return None


def _search(driver, term: str) -> bool:
    """Type the active ingredient into the Principio Activo field and submit.

    Same Livewire form mechanics as the approvals portal: the field has no name/id
    (found by its "Ejemplo: Paracetamol" placeholder), the form carries honey_*
    honeypots (never touch them), and there is no text "Buscar" button — submit via
    the form's icon button after a honeypot-timing wait.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from extractors.pe_approvals import _click_submit, _interactable

    def _find(how, sel):
        try:
            return driver.find_elements(how, sel)
        except Exception:
            return []

    candidates = []
    candidates += _find(By.XPATH, "//input[contains(@placeholder,'Paracetamol')]")
    candidates += _find(By.XPATH, "//input[contains(@placeholder,'rincipio')]")
    if not candidates:
        candidates += [e for e in _find(By.CSS_SELECTOR, "input[type='text']")
                       if not (e.get_attribute("name") or "").startswith("honey")]
    box = next((e for e in candidates if _interactable(e)), None)
    if box is None:
        return False
    try:
        box.clear()
        box.send_keys(term)
        time.sleep(HONEYPOT_WAIT)  # human-like timing before submit
        if not _click_submit(driver, box):
            box.send_keys(Keys.ENTER)
    except Exception:
        return False
    time.sleep(HONEYPOT_WAIT)
    return True


def _click_next(driver) -> bool:
    from selenium.webdriver.common.by import By
    for sel in ["[rel='next']", "a[aria-label='Next']", ".pagination .page-item:not(.disabled) a[rel='next']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            driver.execute_script("arguments[0].click();", el)
            time.sleep(HONEYPOT_WAIT)
            return True
        except Exception:
            continue
    for xp in ["//a[contains(translate(.,'SIGUIENTE','siguiente'),'siguiente')]",
               "//button[contains(translate(.,'SIGUIENTE','siguiente'),'siguiente')]"]:
        try:
            el = driver.find_element(By.XPATH, xp)
            driver.execute_script("arguments[0].click();", el)
            time.sleep(HONEYPOT_WAIT)
            return True
        except Exception:
            continue
    return False


def _harvest(driver, term: str) -> list[dict]:
    table = sb.wait_for_table(driver, TABLE_CSS, timeout=20)
    if table is None:
        return []
    colmap = sb.read_header_map(driver, TABLE_CSS, _COLS) or {}
    out = []
    pages = 0
    seen_first = None
    while pages < MAX_PAGES:
        rows = sb.get_rows(driver, TABLE_CSS)
        if not rows:
            break
        sig = sb.safe_text(rows[0])
        if sig == seen_first:
            break
        seen_first = sig
        for tr in rows:
            cells = sb.cell_texts(tr)
            if not cells:
                continue

            def get(field):
                idx = colmap.get(field, _POS.get(field))
                return cells[idx] if idx is not None and idx < len(cells) else None

            row = {
                "registration_number": get("registration_number"),
                "product_name": get("product_name"),
                "api": get("api"),
                "applicant": get("applicant"),
                "concentration": get("concentration"),
                "dosage_form": get("dosage_form"),
                "process_type": get("process_type"),
                "submission_date": get("submission_date"),
                "status": _composite_status(get("situacion"), get("resultado")),
                "country_code": COUNTRY_CODE,
                "record_type": "SUBMISSION",
                "molecule_search_term": term.upper(),
                "source_url": SOURCE_URL,
            }
            out.append(row)
        pages += 1
        if not _click_next(driver):
            break
    return out


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    from selenium.webdriver.support.ui import WebDriverWait

    errors = config_dict.setdefault("partial_errors", [])
    headless = config_dict.get("headless", False)
    driver = None
    rows: list[dict] = []
    consec = rebuilds = 0
    aborted = False
    try:
        driver = sb.build_driver(headless=headless)
        for m in molecules:
            if aborted or driver is None:
                break
            canon = m["latam_term"].upper()  # tag rows with the canonical term
            for term in config.search_terms(m):  # latam_term + INN-variant aliases
                if aborted or driver is None:
                    break
                try:
                    driver.get(SOURCE_URL)
                    WebDriverWait(driver, 30).until(lambda d: d.execute_script(
                        "return document.readyState") == "complete")
                    time.sleep(HONEYPOT_WAIT)
                    if not _search(driver, term):
                        print(f"    [PE-SUB] search input not found for '{term}'")
                        errors.append(f"PE-SUB {term}: search input not found")
                        continue
                    rows.extend(_harvest(driver, canon))  # search by term, tag canon
                    consec = 0
                except Exception as exc:  # noqa: BLE001
                    driver, consec, rebuilds, aborted = sb.handle_loop_error(
                        driver, exc, "PE-SUB", term, errors, consec, rebuilds,
                        headless=headless)
        print(f"    [PE-SUB] collected {len(rows)} rows")
        return rows
    finally:
        if driver is not None:
            driver.quit()
