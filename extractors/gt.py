"""
gt.py — Guatemala MSPAS (Selenium, PHP server-rendered paginated table).

Portal: https://regsanitario.mspas.gob.gt/reg_sanitario/Vigentes.php
Navigated directly (the public site embeds this as an iframe; hitting the inner
URL avoids context-switching). Searches are by product name — both the molecule
LATAM term and any known brand aliases. Capped at MAX_PAGES per search term.
"""

from __future__ import annotations

import time
from datetime import datetime

import config
from extractors import selenium_base as sb

COUNTRY_CODE = "GT"
SOURCE_URL = config.SOURCE_URLS["gt"]
TABLE_CSS = "table"
MAX_PAGES = 3

# A Guatemalan sanitary registration is granted for a fixed five-year term, so the
# issue date is recoverable from the expiration date the portal does publish.
REGISTRATION_TERM_YEARS = 5


def _issue_from_expiry(expiration) -> str | None:
    """Return the issue date as ``DD/MM/YYYY``: expiration minus the 5-year term.

    Returns ``None`` when the expiration date is missing or unparseable — an absent
    date is honest, an invented one is not.
    """
    import normalize
    parsed = normalize.parse_date(expiration)
    if not parsed:
        return None
    d = datetime.strptime(parsed, "%d/%m/%Y").date()
    try:
        issued = d.replace(year=d.year - REGISTRATION_TERM_YEARS)
    except ValueError:
        # 29 February landing on a non-leap year — step back to the 28th.
        issued = d.replace(year=d.year - REGISTRATION_TERM_YEARS, day=28)
    return issued.strftime("%d/%m/%Y")


_COLS = {
    "registration_number": ["registro"],
    "product_name": ["producto"],
    "api": ["principio activo", "principio_activo"],
    "applicant": ["titular"],
    "manufacturer_country": ["pais de origen", "país de origen", "pais_origen"],
    "manufacturer": ["distribuidor1", "distribuidor 1", "distribuidor"],
    "expiration_date": ["fecha de vencimiento", "vencimiento"],
    "dosage_form": ["forma farmacéutica", "forma farmaceutica"],
    "status": ["estado del producto", "estado"],
    # Not canonical — used only by post-filters (e.g. tadalafil PAH vs ED).
    "_indication_hint": ["clase terapeutica", "clase terapéutica"],
}

_NEXT_XPATHS = [
    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'siguiente')]",
    "//a[normalize-space(.)='>']",
    "//a[contains(@class,'next')]",
    "//li[not(contains(@class,'disabled'))]/a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'siguiente')]",
]


def _do_search(driver, term: str) -> bool:
    """Fill the Vigentes.php filter form and submit, searching by product name.

    The page (confirmed live) exposes form ``frm_filtrar`` with fields
    ``registro / producto / activo / pais``. The portal's *Principio Activo*
    column is empty server-side, so the ``activo`` filter never matches — we
    search ``producto`` instead (the INN appears in the product name for generic
    registrations; brand aliases are searched as extra terms by the caller).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    box = None
    for how, sel in [(By.NAME, "producto"), (By.ID, "producto"),
                     (By.NAME, "activo"), (By.ID, "activo"),
                     (By.CSS_SELECTOR, "input[type='text']"),
                     (By.CSS_SELECTOR, "input[type='search']")]:
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
    except Exception:
        return False
    # Submit via the explicit filter button, then the form, then ENTER.
    for action in (
        lambda: driver.find_element(By.NAME, "btn_filtrar").click(),
        lambda: driver.execute_script(
            "var f=document.getElementById('frm_filtrar')||document.forms[0];"
            "if(f){f.submit();}"),
        lambda: box.send_keys(Keys.ENTER),
    ):
        try:
            action()
            break
        except Exception:
            continue
    time.sleep(2)
    return True


def _click_next(driver) -> bool:
    from selenium.webdriver.common.by import By
    for xp in _NEXT_XPATHS:
        try:
            link = driver.find_element(By.XPATH, xp)
            if link.is_displayed() and link.is_enabled():
                driver.execute_script("arguments[0].click();", link)
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def _harvest_term(driver, term: str) -> list[dict]:
    sb.wait_for_table(driver, TABLE_CSS, timeout=15)
    out = []
    seen_first = None
    for page in range(MAX_PAGES):
        # Re-locate the data table each page — Vigentes.php nests layout tables,
        # so page-wide row selectors would pull in filter-form label cells.
        table, colmap = sb.find_data_table(driver, _COLS)
        if table is None:
            if page == 0:
                print(f"    [GT] no table resolves the 'Registro' column for "
                      f"'{term}' — likely an empty result page")
            break
        rows = sb.element_rows(table)
        if not rows:
            break
        sig = sb.safe_text(rows[0])
        if sig == seen_first:  # page didn't advance
            break
        seen_first = sig
        for tr in rows:
            cells = sb.cell_texts(tr)
            if not cells or sb.is_header_row(cells, colmap, _COLS):
                continue
            row = {field: (cells[idx] if idx < len(cells) else None)
                   for field, idx in colmap.items()}
            row.update({
                "country_code": COUNTRY_CODE,
                "record_type": "APPROVAL",
                "molecule_search_term": term.upper(),
                "source_url": SOURCE_URL,
            })
            # MSPAS publishes no approval date, but a Guatemalan sanitary registration
            # runs for a fixed five-year term, so the issue date is simply the
            # expiration date minus five years. Verified on a live extract: 29/29 rows
            # carry an expiration date, and the derived issue years (2022-2026) are all
            # coherent. This gives day precision — unlike Honduras, where the
            # registration number only encodes month and year.
            if not row.get("approval_date"):
                row["approval_date"] = _issue_from_expiry(row.get("expiration_date"))
            out.append(row)
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
            # Search the LATAM term plus its INN-variant aliases.
            for term in config.search_terms(m):
                if aborted or driver is None:
                    break
                try:
                    driver.get(SOURCE_URL)
                    WebDriverWait(driver, 30).until(lambda d: d.execute_script(
                        "return document.readyState") == "complete")
                    if not _do_search(driver, term):
                        print(f"    [GT] search form not found for '{term}'")
                        errors.append(f"GT {term}: search form not found")
                        continue
                    rows.extend(_harvest_term(driver, m["latam_term"]))
                    consec = 0
                except Exception as exc:  # noqa: BLE001
                    driver, consec, rebuilds, aborted = sb.handle_loop_error(
                        driver, exc, "GT", term, errors, consec, rebuilds,
                        headless=headless)
        print(f"    [GT] collected {len(rows)} rows")
        return rows
    finally:
        if driver is not None:
            driver.quit()
