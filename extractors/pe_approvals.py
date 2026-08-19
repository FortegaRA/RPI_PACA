"""
pe_approvals.py — Peru DIGEMID product approvals.

Portal: https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/
It sits behind a Cloudflare **Managed Challenge** ("Just a moment..." interstitial,
``cf-mitigated: challenge`` — NOT a Turnstile widget, so there is no token to solve;
you must pass the JS challenge and earn a ``cf_clearance`` cookie).

Two strategies:
  * Default — launch Chrome ourselves on --remote-debugging-port=9222 and attach
    Selenium; if the challenge appears we pause for the operator to clear it.
  * ``--pe-stealth`` (config ``pe_stealth``) — drive a SeleniumBase UC-mode
    (undetected) browser that clears the managed challenge automatically, no manual
    step and no remote-debug port. Requires ``pip install seleniumbase`` and a real
    display (UC mode must be headful). VERIFIED working 14/06/2026 (cleared CF and
    pulled 41 rows for a 2-molecule probe). NB the search is a Livewire form with
    honeypots: the active-ingredient field is found by its "Ejemplo: Paracetamol"
    placeholder, we wait HONEYPOT_WAIT, and submit via the form's icon button (no
    text "Buscar"). CF / the form can change — if it stops clearing, escalate to a
    web-unlocker API (Option B2).

Search: "Búsqueda por Composición" tab -> "Principio Activo" field. Paginated up to
MAX_PAGES. Columns (fixed order):
  RS, RS Anterior, Nombre, Forma Farmacéutica, Titular, Rubro, Condición de Venta, Estado
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

import config
from extractors import selenium_base as sb

COUNTRY_CODE = "PE"
SOURCE_URL = config.SOURCE_URLS["pe_approvals"]
DEBUG_PORT = 9222
MAX_PAGES = 50
TABLE_CSS = "table"
HONEYPOT_WAIT = 3.5  # the form has honey_time fields — submitting too fast flags a bot

# Fixed positional fallback when header text cannot be resolved.
_POS = {"registration_number": 0, "product_name": 2, "dosage_form": 3,
        "applicant": 4, "status": 7}
_COLS = {
    "registration_number": ["rs", "registro"],
    "product_name": ["nombre"],
    "dosage_form": ["forma farmacéutica", "forma farmaceutica"],
    "applicant": ["titular"],
    "status": ["estado"],
}

_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]


def _find_chrome() -> str | None:
    for path in _CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return shutil.which("chrome") or shutil.which("google-chrome")


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _debug_browser(port: int) -> str:
    """Return the 'Browser' string of whatever answers CDP on *port* ('' if none).

    Other Chromium-based apps (Electron — e.g. Docker Desktop ships Chromium 134)
    may already be listening on 9222; attaching ChromeDriver to them fails with a
    version mismatch, so we identify the occupant before attaching.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                    timeout=3) as resp:
            return json.loads(resp.read().decode()).get("Browser", "")
    except Exception:
        return ""


def _free_port(start: int = 9223, end: int = 9260) -> int | None:
    for port in range(start, end):
        if not _port_open(port):
            return port
    return None


def _launch_chrome(chrome: str, url: str, port: int) -> tuple:
    profile = tempfile.mkdtemp(prefix="rpi_pe_chrome_")
    proc = subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}",
         f"--user-data-dir={profile}", "--no-first-run",
         "--no-default-browser-check", "--start-maximized", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        if _port_open(port):
            break
        time.sleep(0.5)
    return proc, profile


def _wait_for_captcha(driver, config_dict: dict) -> None:
    """Give the operator a chance to clear a Cloudflare challenge."""
    interactive = not config_dict.get("non_interactive", False)
    # Poll briefly for the search UI to appear on its own.
    for _ in range(20):
        page = driver.page_source.lower()
        if "principio activo" in page or "búsqueda por composición" in page or "composicion" in page:
            return
        time.sleep(1)
    if interactive:
        print("    [PE-APR] If a CAPTCHA is shown, solve it in the Chrome window, "
              "then press Enter here to continue...")
        try:
            input()
        except EOFError:
            pass


def _open_search_tab(driver) -> None:
    from selenium.webdriver.common.by import By
    for xp in [
        "//a[contains(translate(.,'COMPOSICIÓN','composición'),'composición')]",
        "//a[contains(translate(.,'COMPOSICION','composicion'),'composicion')]",
        "//*[contains(text(),'Composición')]",
    ]:
        try:
            driver.find_element(By.XPATH, xp).click()
            time.sleep(1.5)
            return
        except Exception:
            continue


def _search(driver, term: str) -> bool:
    """Type the active ingredient into the 'Búsqueda por Composición' field.

    The field has no name/id — it is identified by its placeholder example
    ("Ejemplo: Paracetamol"). We must NOT touch the form's honey_* honeypot
    inputs (filling them flags a bot), and we wait HONEYPOT_WAIT before submitting
    so the honey_time check sees human-like timing.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    candidates = []
    candidates += driver.find_elements(By.XPATH, "//input[contains(@placeholder,'Paracetamol')]")
    candidates += driver.find_elements(By.XPATH, "//input[contains(@placeholder,'rincipio')]")
    if not candidates:  # last resort: any visible text input that is NOT a honeypot
        candidates += [e for e in driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                       if not (e.get_attribute("name") or "").startswith("honey")]
    box = next((e for e in candidates if _interactable(e)), None)
    if box is None:
        return False
    try:
        box.clear()
        box.send_keys(term)
        time.sleep(HONEYPOT_WAIT)  # human-like timing before submit
        # The Livewire form has no text "Buscar" button — submit via an icon/submit
        # button in the same form, falling back to ENTER.
        if not _click_submit(driver, box):
            box.send_keys(Keys.ENTER)
    except Exception:
        return False
    time.sleep(3)
    return True


def _interactable(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _click_submit(driver, box) -> bool:
    """Click a submit/search control in the form containing *box*."""
    from selenium.webdriver.common.by import By
    try:
        form = box.find_element(By.XPATH, "./ancestor::form[1]")
    except Exception:
        form = driver
    for how, sel in [(By.CSS_SELECTOR, "button[type='submit']"),
                     (By.CSS_SELECTOR, "input[type='submit']"),
                     (By.XPATH, ".//button[.//i[contains(@class,'search') or contains(@class,'lupa') or contains(@class,'fa-search')]]"),
                     (By.XPATH, ".//button[contains(@class,'search') or contains(@wire:click,'buscar') or contains(@wire:click,'search')]"),
                     (By.CSS_SELECTOR, "button")]:
        try:
            btn = form.find_element(how, sel)
            if _interactable(btn):
                driver.execute_script("arguments[0].click();", btn)
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
            row = {}
            for field in _POS:
                idx = colmap.get(field, _POS[field])
                row[field] = cells[idx] if idx < len(cells) else None
            row.update({
                "country_code": COUNTRY_CODE,
                "record_type": "APPROVAL",
                "molecule_search_term": term.upper(),
                "source_url": SOURCE_URL,
            })
            out.append(row)
        pages += 1
        # Advance pagination (DataTables-style next).
        if not _click_next(driver):
            break
    return out


def _click_next(driver) -> bool:
    from selenium.webdriver.common.by import By
    for sel in [".paginate_button.next:not(.disabled)", "a.next:not(.disabled)",
                "li.next:not(.disabled) a"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            driver.execute_script("arguments[0].click();", el)
            time.sleep(2)
            return True
        except Exception:
            continue
    return False


# ── SeleniumBase UC-mode (stealth) path ───────────────────────────────────────
def _is_challenge_page(driver) -> bool:
    """True while Cloudflare's 'Just a moment...' interstitial is showing."""
    try:
        title = (driver.title or "").lower()
    except Exception:
        title = ""
    if "just a moment" in title:
        return True
    try:
        page = (driver.page_source or "").lower()
    except Exception:
        return False
    on_challenge = ("just a moment" in page or "challenge-platform" in page
                    or "cf-mitigated" in page)
    # If the real search UI is present we are past it, regardless of leftovers.
    reached_app = "principio activo" in page or "composici" in page
    return on_challenge and not reached_app


def _default_uc_driver(headless: bool):
    """Create a SeleniumBase UC-mode (undetected) Chrome.

    Raises ImportError when SeleniumBase is not installed. UC mode is forced
    headful — headless UC is far more detectable and the optional PyAutoGUI
    checkbox click needs a real display.
    """
    from seleniumbase import Driver
    return Driver(uc=True, headless=False, locale_code="es")


def _pass_challenge(driver, attempts: int = 3) -> bool:
    """Open the portal through UC reconnect until the CF challenge clears."""
    for i in range(attempts):
        try:
            driver.uc_open_with_reconnect(SOURCE_URL, reconnect_time=6 + 2 * i)
        except Exception:
            try:
                driver.get(SOURCE_URL)
            except Exception:
                pass
        # If a clickable Turnstile checkbox is present, click it (needs a display
        # + pyautogui). Harmless no-op for a pure interstitial.
        try:
            driver.uc_gui_click_captcha()
        except Exception:
            pass
        time.sleep(3)
        if not _is_challenge_page(driver):
            return True
    return not _is_challenge_page(driver)


def _extract_stealth(molecules: list[dict], config_dict: dict) -> list[dict]:
    """Peru via SeleniumBase UC mode — clears the Cloudflare managed challenge
    automatically (no manual CAPTCHA, no remote-debug port)."""
    errors = config_dict.setdefault("partial_errors", [])
    factory = config_dict.get("uc_driver_factory") or _default_uc_driver
    try:
        driver = factory(config_dict.get("headless", False))
    except ImportError:
        msg = ("SeleniumBase not installed — run `pip install --user seleniumbase` "
               "to use --pe-stealth (or drop the flag for the manual flow).")
        print(f"    [PE-APR] {msg}")
        errors.append(f"PE-APR: {msg}")
        return []
    except Exception as exc:  # noqa: BLE001
        msg = sb.err_line(exc)
        print(f"    [PE-APR] could not start UC driver: {msg}")
        errors.append(f"PE-APR: UC driver start failed: {msg}")
        return []

    rows: list[dict] = []
    try:
        if not _pass_challenge(driver):
            msg = "Cloudflare managed challenge not cleared by UC mode"
            print(f"    [PE-APR] {msg} — escalate to a web-unlocker API (Option B2)")
            errors.append(f"PE-APR: {msg}")
            return []
        print("    [PE-APR] Cloudflare challenge cleared (UC mode)")
        _open_search_tab(driver)

        # NB: no per-term driver.get(SOURCE_URL) here. Reloading the CF-protected
        # homepage before every search term (~30-40 times for the full molecule
        # panel) reads as automated traffic and gets the session re-challenged
        # mid-run (seen live 28/07/2026, aborted after 4 consecutive re-challenge
        # failures). Instead we stay on the page and just re-open the search tab
        # between terms — same in-page interaction _harvest leaves behind after
        # pagination, no new navigation.
        consec = 0
        for m in molecules:
            if consec >= 4:
                break
            canon = m["latam_term"].upper()
            for term in config.search_terms(m):
                if consec >= 4:
                    break
                try:
                    if _is_challenge_page(driver) and not _pass_challenge(driver, attempts=4):
                        raise RuntimeError("re-challenged and could not clear")
                    _open_search_tab(driver)
                    if not _search(driver, term):
                        continue
                    rows.extend(_harvest(driver, canon))  # search by term, tag canon
                    consec = 0
                except Exception as exc:  # noqa: BLE001
                    print(f"    [PE-APR] error for {term}: {sb.err_line(exc)}")
                    errors.append(f"PE-APR {term}: {sb.err_line(exc)}")
                    consec += 1
        print(f"    [PE-APR] collected {len(rows)} rows (stealth)")
        return rows
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def extract(molecules: list[dict], config_dict: dict) -> list[dict]:
    # Stealth path: SeleniumBase UC mode auto-clears the managed challenge.
    if config_dict.get("pe_stealth"):
        return _extract_stealth(molecules, config_dict)

    errors = config_dict.setdefault("partial_errors", [])
    chrome = _find_chrome()
    proc = profile = driver = None
    rows: list[dict] = []
    try:
        # ── Pick a debug port. 9222 may be squatted by another Chromium-based
        # app (e.g. Docker Desktop's Electron shell) — only reuse it if the
        # occupant identifies itself as real Chrome.
        port = DEBUG_PORT
        if _port_open(port):
            browser = _debug_browser(port)
            if not browser.startswith("Chrome/"):
                alt = _free_port()
                print(f"    [PE-APR] port {port} is occupied by "
                      f"'{browser or 'an unknown app'}' — using port {alt} instead")
                port = alt
        if port is None:
            errors.append("PE-APR: no free debug port available")
            return []

        if not _port_open(port):
            if chrome is None:
                msg = ("Chrome executable not found. Open Chrome manually with "
                       f"--remote-debugging-port={port}, solve the CAPTCHA, then re-run.")
                print(f"    [PE-APR] {msg}")
                errors.append(f"PE-APR: {msg}")
                return []
            proc, profile = _launch_chrome(chrome, SOURCE_URL, port)
        if not _port_open(port):
            msg = (f"Chrome remote-debug port {port} not reachable. Open Chrome with "
                   f"--remote-debugging-port={port}, solve the CAPTCHA, then re-run.")
            print(f"    [PE-APR] {msg}")
            errors.append(f"PE-APR: {msg}")
            return []

        try:
            driver = sb.build_driver(debugger_address=f"127.0.0.1:{port}")
        except Exception as exc:  # SessionNotCreated: version mismatch etc.
            msg = sb.err_line(exc)
            print(f"    [PE-APR] could not attach to Chrome on port {port}: {msg}")
            print("    [PE-APR] If this is a ChromeDriver/Chrome version mismatch, "
                  "update Chrome (or clear the Selenium driver cache) and re-run. "
                  f"Otherwise open Chrome manually with --remote-debugging-port={port}, "
                  "solve the CAPTCHA, then re-run.")
            errors.append(f"PE-APR: attach failed: {msg}")
            return []

        driver.get(SOURCE_URL)
        _wait_for_captcha(driver, config_dict)

        consec = rebuilds = 0
        abort = False
        for m in molecules:
            if abort or driver is None:
                break
            canon = m["latam_term"].upper()  # tag rows with the canonical term
            for term in config.search_terms(m):  # latam_term + INN-variant aliases
                if abort or driver is None:
                    break
                try:
                    driver.get(SOURCE_URL)
                    time.sleep(1.5)
                    _open_search_tab(driver)
                    if not _search(driver, term):
                        continue
                    rows.extend(_harvest(driver, canon))  # search by term, tag canon
                    consec = 0
                except Exception as exc:  # noqa: BLE001
                    # NB: a relaunched driver here is a plain (non-debug-port) Chrome —
                    # if the CAPTCHA reappears the remaining terms will return 0 rows,
                    # which the abort-after-N-failures policy turns into a clean stop.
                    driver, consec, rebuilds, abort = sb.handle_loop_error(
                        driver, exc, "PE-APR", term, errors, consec, rebuilds)
        print(f"    [PE-APR] collected {len(rows)} rows")
        return rows
    finally:
        # Detach Selenium without killing the user's Chrome unless we launched it.
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        if profile and os.path.isdir(profile):
            shutil.rmtree(profile, ignore_errors=True)
