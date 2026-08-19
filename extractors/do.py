"""
do.py — Dominican Republic DIGEMAPS (Selenium, Angular SPA).

Portal: https://consultas.digemaps.gob.do/registrosanitario
Search type dropdown -> DCI (option value "3"), then the molecule term. DIGEMAPS
publishes no explicit status column, so status is derived from the expiration
date relative to today (>= today -> APPROVED, else EXPIRED).
"""

from __future__ import annotations

import time
from datetime import date, datetime

import config
from extractors import selenium_base as sb

COUNTRY_CODE = "DO"
SOURCE_URL = config.SOURCE_URLS["do"]
TABLE_CSS = "table"

_COLS = {
    "registration_number": ["registro sanitario", "registro"],
    "product_name": ["nombre producto", "nombre del producto", "producto"],
    "applicant": ["representante"],
    "manufacturer": ["fabricante"],
    "approval_date": ["fecha generacion", "fecha generación", "fecha de generacion"],
    "expiration_date": ["fecha vencimiento", "fecha de vencimiento", "vencimiento"],
}


def _derive_status(expiration_raw) -> str | None:
    if not expiration_raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            exp = datetime.strptime(str(expiration_raw).strip(), fmt).date()
            return "APPROVED" if exp >= date.today() else "EXPIRED"
        except ValueError:
            continue
    return None


def _select_dci_and_search(driver, term: str) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import Select

    # Choose DCI (option value "3") in the search-type dropdown if present.
    try:
        sel_el = driver.find_element(By.CSS_SELECTOR, "select")
        try:
            Select(sel_el).select_by_value("3")
        except Exception:
            Select(sel_el).select_by_visible_text("DCI")
        time.sleep(1)
    except Exception:
        pass

    box = None
    for how, sel in [(By.CSS_SELECTOR, "input[type='text']"),
                     (By.CSS_SELECTOR, "input[type='search']"),
                     (By.CSS_SELECTOR, "input")]:
        try:
            box = driver.find_element(how, sel)
            break
        except Exception:
            continue
    if box is None:
        return False
    try:
        box.clear()
        box.send_keys(term)
        box.send_keys(Keys.ENTER)
    except Exception:
        return False

    # Also try an explicit search button.
    for xp in ["//button[contains(translate(., 'BUSCAR', 'buscar'),'buscar')]",
               "//button[contains(translate(., 'CONSULTAR', 'consultar'),'consultar')]",
               "//button[@type='submit']"]:
        try:
            driver.find_element(By.XPATH, xp).click()
            break
        except Exception:
            continue
    time.sleep(3)
    return True


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
                    time.sleep(2)  # let Angular bootstrap
                    if not _select_dci_and_search(driver, term):
                        print(f"    [DO] search controls not found for '{term}'")
                        errors.append(f"DO {term}: search controls not found")
                        continue
                    table = sb.wait_for_table(driver, TABLE_CSS, timeout=20)
                    if table is None:
                        continue
                    colmap = sb.read_header_map(driver, TABLE_CSS, _COLS)
                    if "registration_number" not in colmap:
                        print(f"    [DO] could not resolve 'Registro Sanitario' column "
                              f"(resolved: {sorted(colmap)}) — skipping '{term}'")
                        continue
                    for tr in sb.get_rows(driver, TABLE_CSS):
                        cells = sb.cell_texts(tr)
                        if not cells or sb.is_header_row(cells, colmap, _COLS):
                            continue
                        row = {field: (cells[idx] if idx < len(cells) else None)
                               for field, idx in colmap.items()}
                        row["status"] = _derive_status(row.get("expiration_date"))
                        row.update({
                            "country_code": COUNTRY_CODE,
                            "record_type": "APPROVAL",
                            "molecule_search_term": canon,
                            "source_url": SOURCE_URL,
                        })
                        rows.append(row)
                    consec = 0
                except Exception as exc:  # noqa: BLE001
                    driver, consec, rebuilds, aborted = sb.handle_loop_error(
                        driver, exc, "DO", term, errors, consec, rebuilds,
                        headless=headless)
        print(f"    [DO] collected {len(rows)} rows")
        return rows
    finally:
        if driver is not None:
            driver.quit()
