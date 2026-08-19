"""
selenium_base.py — Shared Chrome/Selenium helpers for the browser-driven extractors.

Selenium is imported defensively so this module (and any extractor that imports it)
can still be imported in an environment where Selenium is not installed. The actual
import error only surfaces when ``build_driver`` is called, where the orchestrator's
per-country try/except turns it into a clean ERROR row instead of a crash.
"""

from __future__ import annotations

import os
import time
from typing import Iterator, Optional

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        StaleElementReferenceException,
        WebDriverException,
        NoSuchElementException,
    )
    SELENIUM_AVAILABLE = True
    _IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - depends on environment
    SELENIUM_AVAILABLE = False
    _IMPORT_ERROR = exc

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# CDP payload that scrubs the most common automation tells before any page script
# on the document runs.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es', 'en']});
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _q(p)
  );
}
"""


def _require_selenium() -> None:
    if not SELENIUM_AVAILABLE:
        raise RuntimeError(
            "Selenium is not available in this environment "
            f"({_IMPORT_ERROR}). Install requirements.txt or pass --no-selenium."
        )


def build_driver(headless: bool = False, download_dir: Optional[str] = None,
                 debugger_address: Optional[str] = None):
    """Create a Chrome WebDriver with standard anti-detection options.

    If *download_dir* is given, Chrome is configured to download files there
    automatically (no prompt). If *debugger_address* (``host:port``) is given,
    Selenium attaches to an already-running Chrome instead of launching one — used
    by the Peru-approvals CAPTCHA workflow.
    """
    _require_selenium()
    options = Options()

    if debugger_address:
        # Attach to an externally launched Chrome (remote-debug CAPTCHA bypass).
        options.add_experimental_option("debuggerAddress", debugger_address)
        return webdriver.Chrome(options=options)

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=es-ES")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={DEFAULT_UA}")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    if download_dir:
        download_dir = os.path.abspath(download_dir)
        os.makedirs(download_dir, exist_ok=True)
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
        options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    try:
        inject_stealth(driver)
    except Exception:
        pass  # stealth is best-effort
    return driver


def inject_stealth(driver) -> None:
    """Patch navigator.webdriver, window.chrome, plugins, languages, permissions."""
    _require_selenium()
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": _STEALTH_JS})
    except WebDriverException:
        # Fallback: run once against the current document.
        try:
            driver.execute_script(_STEALTH_JS)
        except WebDriverException:
            pass


def wait_for_table(driver, css_selector: str, timeout: int = 30):
    """Wait until a table matching *css_selector* has at least one tbody row.

    Returns the table WebElement, or ``None`` on timeout.
    """
    _require_selenium()
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: _has_rows(d, css_selector))
        return driver.find_element(By.CSS_SELECTOR, css_selector)
    except TimeoutException:
        return None


def _has_rows(driver, css_selector: str) -> bool:
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, f"{css_selector} tbody tr")
        return len(rows) > 0
    except (StaleElementReferenceException, NoSuchElementException, WebDriverException):
        return False


def get_rows(driver, table_css: str) -> list:
    """Return the current tbody ``tr`` elements for a table CSS selector."""
    _require_selenium()
    return driver.find_elements(By.CSS_SELECTOR, f"{table_css} tbody tr")


def paginate_table(driver, table_css: str, next_btn_selector: str,
                   page_limit: int = 50, settle: float = 1.5) -> Iterator[list]:
    """Yield table rows page by page.

    Yields the current page's rows, then clicks the *next* button and waits for the
    table to refresh. Stops when the next button is missing/disabled or *page_limit*
    is reached.
    """
    _require_selenium()
    page = 0
    while page < page_limit:
        rows = get_rows(driver, table_css)
        yield rows
        page += 1

        nxt = _find_next_button(driver, next_btn_selector)
        if nxt is None or not _is_clickable(nxt):
            break

        first_signature = rows[0].text if rows else ""
        try:
            driver.execute_script("arguments[0].click();", nxt)
        except WebDriverException:
            break

        # Wait for the first row to change (table refreshed) or a short timeout.
        try:
            WebDriverWait(driver, 15).until(
                lambda d: (get_rows(d, table_css)[0].text if get_rows(d, table_css)
                           else "") != first_signature)
        except (TimeoutException, WebDriverException, StaleElementReferenceException):
            pass
        time.sleep(settle)


def _find_next_button(driver, selector: str):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector)
    except (NoSuchElementException, WebDriverException):
        return None


def _is_clickable(element) -> bool:
    try:
        if not element.is_enabled() or not element.is_displayed():
            return False
        cls = (element.get_attribute("class") or "").lower()
        aria = (element.get_attribute("aria-disabled") or "").lower()
        return "disabled" not in cls and aria != "true"
    except WebDriverException:
        return False


def safe_text(element) -> str:
    """Return ``element.text`` stripped, or '' on any Selenium error."""
    try:
        return (element.text or "").strip()
    except Exception:
        return ""


def err_line(exc) -> str:
    """First line of a (Selenium) exception — drops the chromedriver stacktrace."""
    msg = getattr(exc, "msg", None) or str(exc) or exc.__class__.__name__
    return str(msg).strip().splitlines()[0][:300]


def session_alive(driver) -> bool:
    """True if the WebDriver session still responds to commands."""
    if driver is None:
        return False
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def handle_loop_error(driver, exc, tag: str, context: str, errors: list,
                      consec: int, rebuilds: int, max_consec: int = 4,
                      max_rebuilds: int = 2, **build_kwargs):
    """Shared error policy for per-molecule Selenium loops.

    Logs one clean line, records the error, relaunches Chrome when the session
    died (up to *max_rebuilds* times), and aborts after *max_consec* consecutive
    failures (network/portal down — no point iterating 28 molecules).

    Returns ``(driver_or_None, consec, rebuilds, abort)``.
    """
    msg = err_line(exc)
    print(f"    [{tag}] error for {context}: {msg}")
    errors.append(f"{tag} {context}: {msg}")
    consec += 1

    if not session_alive(driver):
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass
        rebuilds += 1
        if rebuilds > max_rebuilds:
            print(f"    [{tag}] browser died {rebuilds} times — aborting extractor")
            return None, consec, rebuilds, True
        try:
            driver = build_driver(**build_kwargs)
            print(f"    [{tag}] browser session died — relaunched Chrome")
        except Exception as exc2:
            print(f"    [{tag}] could not relaunch Chrome: {err_line(exc2)}")
            errors.append(f"{tag}: relaunch failed: {err_line(exc2)}")
            return None, consec, rebuilds, True

    if consec >= max_consec:
        print(f"    [{tag}] {consec} consecutive failures — aborting "
              f"(network or portal down?)")
        return driver, consec, rebuilds, True
    return driver, consec, rebuilds, False


def read_header_map(driver, table_css: str, candidates: dict) -> dict:
    """Map canonical field -> column index by matching header cell text.

    *candidates* is ``{field: [possible header strings]}``. Matching is
    case-insensitive and substring-based (a header "Estado del Producto" matches
    the candidate "Estado del Producto" or "Estado").

    Headers are read from ``thead th``/``thead td``; when the table has no
    ``<thead>`` (common on older PHP portals like Guatemala's), the first table
    row's cells are used instead — pair with :func:`is_header_row` to skip that
    row during harvesting.
    """
    _require_selenium()
    headers = driver.find_elements(By.CSS_SELECTOR, f"{table_css} thead th")
    if not headers:
        headers = driver.find_elements(By.CSS_SELECTOR, f"{table_css} thead td")
    texts = [safe_text(h).lower() for h in headers]
    if not any(texts):
        # No <thead>: fall back to the first row's cells as headers.
        try:
            first_rows = driver.find_elements(By.CSS_SELECTOR, f"{table_css} tr")
            if first_rows:
                cells = first_rows[0].find_elements(By.CSS_SELECTOR, "th, td")
                texts = [safe_text(c).lower() for c in cells]
        except Exception:
            texts = []
    resolved: dict = {}
    for field, options in candidates.items():
        for opt in options:
            ol = opt.strip().lower()
            for idx, htext in enumerate(texts):
                if htext == ol or ol in htext:
                    resolved[field] = idx
                    break
            if field in resolved:
                break
    return resolved


def find_data_table(driver, candidates: dict, required: str = "registration_number"):
    """Locate the table that actually holds the result data.

    Portals built from nested layout tables (e.g. Guatemala's Vigentes.php) make
    page-wide selectors like ``table tbody tr`` match form-layout rows too. This
    scores every ``<table>`` element individually — headers from its ``thead`` or
    its first row — and returns ``(table_element, colmap)`` for the best match.
    The score is the number of DISTINCT column indexes resolved, which naturally
    rejects wrapper tables whose single mega-cell substring-matches everything.

    Returns ``(None, {})`` when no table resolves the *required* field.
    """
    _require_selenium()
    best_el, best_map, best_score = None, {}, 0
    for tbl in driver.find_elements(By.TAG_NAME, "table"):
        try:
            headers = (tbl.find_elements(By.CSS_SELECTOR, "thead th")
                       or tbl.find_elements(By.CSS_SELECTOR, "thead td"))
            texts = [safe_text(h).lower() for h in headers]
            if not any(texts):
                trs = tbl.find_elements(By.CSS_SELECTOR, "tr")
                if trs:
                    cells = trs[0].find_elements(By.CSS_SELECTOR, "th, td")
                    texts = [safe_text(c).lower() for c in cells]
        except Exception:
            continue
        if not any(texts):
            continue
        colmap: dict = {}
        for field, options in candidates.items():
            for opt in options:
                ol = opt.strip().lower()
                hit = next((i for i, h in enumerate(texts) if h == ol or ol in h), None)
                if hit is not None:
                    colmap[field] = hit
                    break
        if required not in colmap:
            continue
        score = len(set(colmap.values()))
        if score > best_score:
            best_el, best_map, best_score = tbl, colmap, score
    return best_el, best_map


def element_rows(table_el) -> list:
    """Rows of one specific table element (not page-wide like get_rows)."""
    _require_selenium()
    try:
        rows = table_el.find_elements(By.CSS_SELECTOR, "tbody tr")
        return rows or table_el.find_elements(By.TAG_NAME, "tr")
    except Exception:
        return []


def is_header_row(cells: list, colmap: dict, candidates: dict) -> bool:
    """True when a harvested row is actually the header row (thead-less tables).

    Checks whether the cells at the resolved column indexes contain the candidate
    header texts themselves (e.g. the cell at the registration column literally
    says "Registro").
    """
    if not colmap or not cells:
        return False
    hits = 0
    for field, idx in colmap.items():
        if idx >= len(cells):
            continue
        cell = str(cells[idx]).strip().lower()
        if not cell:
            continue
        for cand in candidates.get(field, []):
            cl = cand.strip().lower()
            if cell == cl or cl in cell:
                hits += 1
                break
    return hits >= min(2, len(colmap))


def cell_texts(row_element) -> list:
    """Return the stripped text of each ``td`` in a table row."""
    _require_selenium()
    try:
        cells = row_element.find_elements(By.TAG_NAME, "td")
        return [safe_text(c) for c in cells]
    except Exception:
        return []


def clear_downloads(download_dir: str, *names: str) -> None:
    """Delete pre-existing files so Chrome won't append ' (1)' suffixes.

    Removes exact *names* plus any ``*.crdownload`` temp files in the directory.
    """
    if not download_dir or not os.path.isdir(download_dir):
        return
    targets = set(names)
    for fname in os.listdir(download_dir):
        full = os.path.join(download_dir, fname)
        if fname in targets or fname.endswith(".crdownload"):
            try:
                os.remove(full)
            except OSError:
                pass


def wait_for_download(download_dir: str, expected_name: Optional[str] = None,
                      timeout: int = 90, exts: tuple = (".xlsx", ".xls", ".csv")) -> Optional[str]:
    """Block until a download completes *during this call*; return path or ``None``.

    Completion = no ``.crdownload`` temp file present and a matching finished file
    exists. If *expected_name* is given it must match; otherwise the newest file
    with one of *exts* is returned.

    A file is only accepted when it was written **after this call started**. Without
    that guard a stale workbook left in a shared download dir counts as a successful
    download: that is exactly how Costa Rica silently returned Honduras' registry for
    months (its own download never happened, and the newest ``.xlsx`` in the shared
    folder was ``MedicamentosArsa.xlsx``). A failed download must return ``None``.
    """
    started = time.time()
    deadline = started + timeout

    def _fresh(path: str) -> bool:
        try:
            # 2s of slack absorbs coarse filesystem timestamp resolution.
            return os.path.getmtime(path) >= started - 2
        except OSError:
            return False

    while time.time() < deadline:
        if any(f.endswith(".crdownload") for f in os.listdir(download_dir)):
            time.sleep(1)
            continue
        if expected_name:
            candidate = os.path.join(download_dir, expected_name)
            if os.path.exists(candidate) and _fresh(candidate):
                return candidate
        else:
            finished = [os.path.join(download_dir, f) for f in os.listdir(download_dir)
                        if f.lower().endswith(exts) and _fresh(os.path.join(download_dir, f))]
            if finished:
                return max(finished, key=os.path.getmtime)
        time.sleep(1)
    return None
