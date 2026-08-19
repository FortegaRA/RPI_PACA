"""
Shared test doubles for the RPI_Cluster unit tests.

These let every extractor run with no network and no real Chrome, so we can assert
the central contract:

    * "no record for this molecule"  -> extractor returns []  AND leaves
      config["partial_errors"] empty            (a clean EMPTY)
    * "something went wrong fetching" -> extractor records a message in
      config["partial_errors"]                  (an ERROR / FAILED / PARTIAL)
"""

from __future__ import annotations


# ── HTTP doubles ──────────────────────────────────────────────────────────────
class FakeHTTPError(Exception):
    """Stands in for requests.HTTPError raised by raise_for_status()."""


class FakeConnError(Exception):
    """Stands in for a dropped connection / DNS failure."""


class FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text="", headers=None,
                 content=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}
        # Bytes body (e.g. an XLSX download). Falls back to encoding `text`.
        if content is not None:
            self.content = content
        else:
            self.content = text.encode("utf-8") if isinstance(text, str) else (text or b"")

    def json(self):
        if self._json is None:
            raise ValueError("response is not JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPError(f"HTTP {self.status_code}")

    # context-manager support (HN streams with `with session.get(...) as r`)
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, chunk_size=1):
        yield self.text.encode("utf-8") if isinstance(self.text, str) else self.text


class FakeSession:
    """Configurable stand-in for requests.Session.

    *handler* is ``f(method, url, **kwargs) -> FakeResponse``. If *raise_exc* is
    set, every call raises it (simulates a total network outage).
    """

    def __init__(self, handler=None, raise_exc=None, default=None):
        self.handler = handler
        self.raise_exc = raise_exc
        self.default = default if default is not None else FakeResponse()
        self.calls = []
        self.headers = {}

    def _do(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.handler is not None:
            return self.handler(method, url, **kw)
        return self.default

    def get(self, url, **kw):
        return self._do("GET", url, **kw)

    def post(self, url, **kw):
        return self._do("POST", url, **kw)

    def mount(self, *a, **k):
        pass


# ── Selenium doubles ──────────────────────────────────────────────────────────
class FakeWebDriverException(Exception):
    """Stands in for selenium WebDriverException / invalid session id, etc."""


class FakeElement:
    def __init__(self, text="", attrs=None, tag="input"):
        self.text = text
        self.tag_name = tag
        self._attrs = attrs or {}

    def clear(self):
        pass

    def send_keys(self, *a):
        pass

    def click(self):
        pass

    def submit(self):
        pass

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def get_attribute(self, key):
        return self._attrs.get(key)

    def find_elements(self, *a, **k):
        return []

    def find_element(self, *a, **k):
        raise FakeWebDriverException("no such element")


class FakeDriver:
    """Minimal WebDriver stand-in.

    *raise_on_get* simulates a portal/network failure on navigation.
    *has_search_box* controls whether find_element returns a usable input.
    *dead* makes session-liveness checks fail (invalid session id).
    """

    def __init__(self, *, raise_on_get=None, has_search_box=True, dead=False,
                 rows=None, tables=None, page_source="<html></html>"):
        self.raise_on_get = raise_on_get
        self.has_search_box = has_search_box
        self.dead = dead
        self.rows = rows or []
        self.tables = tables or []
        self._page_source = page_source
        self.quit_called = False
        self._url = "http://fake.local/"

    @property
    def current_url(self):
        if self.dead:
            raise FakeWebDriverException("invalid session id")
        return self._url

    @property
    def page_source(self):
        return self._page_source

    def get(self, url):
        if self.raise_on_get is not None:
            raise self.raise_on_get
        self._url = url

    def execute_script(self, script, *args):
        # WebDriverWait(...).until(lambda d: d.execute_script(...) == "complete")
        return "complete"

    def execute_cdp_cmd(self, *a, **k):
        return {}

    def find_element(self, *a, **k):
        if self.has_search_box:
            return FakeElement()
        raise FakeWebDriverException("no such element")

    def find_elements(self, by=None, value=None):
        sel = str(value or "").lower()
        if "tr" in sel:
            return self.rows
        if "table" in sel:
            return self.tables
        # Search-field lookups (placeholder/input) yield one fake box when present.
        if "input" in sel or "placeholder" in sel:
            return [FakeElement()] if self.has_search_box else []
        return []

    def quit(self):
        self.quit_called = True
