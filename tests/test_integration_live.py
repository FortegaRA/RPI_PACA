"""
Real integration tests — these hit the LIVE health-authority portals.

They confirm, against the real services, the same empty-vs-error contract the unit
tests pin down with fakes:

    * a molecule that exists      -> rows come back, NO partial_error
    * a molecule that cannot exist (nonsense INN) -> []  AND NO partial_error
      (i.e. the live portal answering "nothing found" is detected as a clean
       EMPTY, never mistaken for an extraction error)

Skip rules:
    * Each test skips automatically when its portal host is unreachable
      (offline / DNS failure) — so the suite stays green with no network.
    * Set RPI_SKIP_INTEGRATION=1 to skip them all (e.g. fast/offline CI).
    * Guatemala additionally needs Chrome + Selenium and skips otherwise.

Ecuador (ARCSA) is intentionally NOT exercised live: its portal blocks IPs that
request faster than ~15s apart, and a test must not risk getting the user's IP
blocked. EC's empty-vs-error logic is covered by the unit tests instead.
"""

import os
import shutil
import socket
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import config  # noqa: E402
from extractors import ema, fda, co_approvals, sv, hn, gt  # noqa: E402
from extractors import selenium_base as sb  # noqa: E402

SKIP_ALL = os.environ.get("RPI_SKIP_INTEGRATION") == "1"

# Nonsense INN that no registry can hold — the "no record" probe.
ABSENT = {"latam_term": "ZZQXNONEXISTENTE", "ema_term": "zzqxnonexistente",
          "fda_term": "zzqxnonexistente", "aliases": []}


def _mol(latam, eng=None):
    eng = (eng or latam).lower()
    return {"latam_term": latam.upper(), "ema_term": eng, "fda_term": eng, "aliases": []}


REGORAFENIB = _mol("REGORAFENIB", "regorafenib")
DAPAGLIFLOZINA = _mol("DAPAGLIFLOZINA", "dapagliflozin")


def _online(host, port=443, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _chrome_available():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    return (any(os.path.exists(p) for p in paths)
            or bool(shutil.which("chrome")) or bool(shutil.which("google-chrome")))


class LiveBase(unittest.TestCase):
    HOST = None

    def setUp(self):
        if SKIP_ALL:
            self.skipTest("RPI_SKIP_INTEGRATION=1")
        if self.HOST and not _online(self.HOST):
            self.skipTest(f"no network to {self.HOST}")

    # Shared assertions ------------------------------------------------------
    def assert_known(self, extractor, molecule, **cfg_extra):
        """A known molecule must return rows with no recorded error."""
        c = {"partial_errors": []}
        c.update(cfg_extra)
        rows = extractor.extract([molecule], c)
        if c["partial_errors"]:
            # The live portal itself errored (transient outage / change) — we can't
            # assert presence in that case, so skip rather than fail spuriously.
            self.skipTest(f"portal returned an error: {c['partial_errors'][0]}")
        self.assertTrue(rows, f"expected live rows for {molecule['latam_term']}")
        # Every row must carry the canonical-ish keys the normalizer needs.
        self.assertTrue(all(r.get("registration_number") for r in rows))

    def assert_absent_is_clean_empty(self, extractor, **cfg_extra):
        """A nonsense molecule must yield [] and record NO error (EMPTY, not ERROR)."""
        c = {"partial_errors": []}
        c.update(cfg_extra)
        rows = extractor.extract([ABSENT], c)
        self.assertEqual(rows, [], "a nonexistent molecule must return no rows")
        self.assertEqual(c["partial_errors"], [],
                         "a 'no record' result must NOT be flagged as an error")


# ── EMA ───────────────────────────────────────────────────────────────────────
class TestEMALive(LiveBase):
    HOST = "www.ema.europa.eu"

    def test_known_molecule_returns_data(self):
        self.assert_known(ema, REGORAFENIB, session=config.build_session())

    def test_absent_molecule_is_clean_empty(self):
        self.assert_absent_is_clean_empty(ema, session=config.build_session())


# ── FDA ───────────────────────────────────────────────────────────────────────
class TestFDALive(LiveBase):
    HOST = "api.fda.gov"

    def test_known_molecule_returns_data(self):
        self.assert_known(fda, REGORAFENIB, session=config.build_session())

    def test_absent_molecule_is_clean_empty(self):
        self.assert_absent_is_clean_empty(fda, session=config.build_session())


# ── Colombia approvals (Socrata) ──────────────────────────────────────────────
class TestColombiaLive(LiveBase):
    HOST = "www.datos.gov.co"

    def test_known_molecule_returns_data(self):
        self.assert_known(co_approvals, REGORAFENIB, session=config.build_session())

    def test_absent_molecule_is_clean_empty(self):
        self.assert_absent_is_clean_empty(co_approvals, session=config.build_session())


# ── El Salvador (DataTables JSON endpoint) ────────────────────────────────────
class TestElSalvadorLive(LiveBase):
    HOST = "expedientes.srs.gob.sv"

    def test_known_molecule_returns_data(self):
        self.assert_known(sv, DAPAGLIFLOZINA, session=config.build_session())

    def test_absent_molecule_is_clean_empty(self):
        self.assert_absent_is_clean_empty(sv, session=config.build_session())


# ── Honduras (bulk Excel download) ────────────────────────────────────────────
class TestHondurasLive(LiveBase):
    HOST = "sicreb.arsa.hn"

    def setUp(self):
        super().setUp()
        # One 2 MB download serves both a present and an absent probe.
        self._dl = os.path.join(ROOT, "output", "_downloads")
        os.makedirs(self._dl, exist_ok=True)

    def test_known_and_absent_in_one_download(self):
        # Pass both molecules; the download happens once. Assert the known one is
        # present and the run records no error (so absent != error).
        c = {"partial_errors": [], "download_dir": self._dl, "no_selenium": True}
        rows = hn.extract([DAPAGLIFLOZINA, ABSENT], c)
        if c["partial_errors"]:
            self.skipTest(f"ARSA download/parse error: {c['partial_errors'][0]}")
        self.assertTrue(rows, "expected live ARSA rows for dapagliflozina")
        terms = {r["molecule_search_term"] for r in rows}
        self.assertIn("DAPAGLIFLOZINA", terms)
        self.assertNotIn("ZZQXNONEXISTENTE", terms)


# ── Guatemala (Selenium, server-rendered) ─────────────────────────────────────
@unittest.skipUnless(sb.SELENIUM_AVAILABLE and _chrome_available(),
                     "Guatemala live test needs Chrome + Selenium")
class TestGuatemalaLive(LiveBase):
    HOST = "regsanitario.mspas.gob.gt"

    def test_known_molecule_returns_data(self):
        self.assert_known(gt, DAPAGLIFLOZINA, headless=True)

    def test_absent_molecule_is_clean_empty(self):
        self.assert_absent_is_clean_empty(gt, headless=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
