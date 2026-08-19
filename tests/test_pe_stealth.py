"""
Peru --pe-stealth (SeleniumBase UC mode) integration — tested without a browser
via the `uc_driver_factory` injection hook.

We cannot test whether UC actually clears live Cloudflare (that needs a real
browser + the live challenge, and is probabilistic). We DO pin down the wiring:
challenge detection, graceful handling when SeleniumBase is missing, a clean error
when the challenge won't clear, and a clean empty when it clears but finds no rows.
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
from extractors import pe_approvals as pe  # noqa: E402

MOL = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
        "fda_term": "regorafenib", "aliases": []}]


class FakeUC:
    """Minimal SeleniumBase UC-mode driver stand-in."""

    def __init__(self, challenge=False, has_box=True):
        self._challenge = challenge
        self.has_box = has_box
        self.quit_called = False
        self.get_calls = 0

    @property
    def title(self):
        return "Just a moment..." if self._challenge else "DIGEMID - Productos"

    @property
    def page_source(self):
        return ("<html>challenge-platform cf-mitigated</html>" if self._challenge
                else "<html>Búsqueda por Composición — Principio Activo</html>")

    def uc_open_with_reconnect(self, url, reconnect_time=6):
        pass

    def uc_gui_click_captcha(self):
        pass

    def get(self, url):
        self.get_calls += 1

    def execute_script(self, *a, **k):
        return "complete"

    def find_element(self, *a, **k):
        if self.has_box:
            return fk.FakeElement()
        raise fk.FakeWebDriverException("no such element")

    def find_elements(self, *a, **k):
        return []

    def quit(self):
        self.quit_called = True


class TestChallengeDetection(unittest.TestCase):
    def test_interstitial_title_is_challenge(self):
        self.assertTrue(pe._is_challenge_page(FakeUC(challenge=True)))

    def test_real_app_page_is_not_challenge(self):
        self.assertFalse(pe._is_challenge_page(FakeUC(challenge=False)))


class TestStealthWiring(unittest.TestCase):
    def test_missing_seleniumbase_is_clean_error(self):
        def factory(headless):
            raise ImportError("No module named 'seleniumbase'")
        cfg = {"partial_errors": [], "pe_stealth": True, "uc_driver_factory": factory}
        rows = pe.extract(MOL, cfg)
        self.assertEqual(rows, [])
        self.assertTrue(any("SeleniumBase not installed" in e for e in cfg["partial_errors"]))

    def test_challenge_not_cleared_records_error(self):
        uc = FakeUC(challenge=True)  # stays on the interstitial forever
        cfg = {"partial_errors": [], "pe_stealth": True,
               "uc_driver_factory": lambda h: uc}
        with mock.patch("extractors.pe_approvals.time.sleep"):
            rows = pe.extract(MOL, cfg)
        self.assertEqual(rows, [])
        self.assertTrue(any("not cleared" in e for e in cfg["partial_errors"]))
        self.assertTrue(uc.quit_called)

    def test_cleared_but_no_rows_is_clean_empty(self):
        uc = FakeUC(challenge=False, has_box=True)
        cfg = {"partial_errors": [], "pe_stealth": True,
               "uc_driver_factory": lambda h: uc}
        with mock.patch("extractors.pe_approvals.time.sleep"), \
             mock.patch("extractors.selenium_base.wait_for_table", return_value=None):
            rows = pe.extract(MOL, cfg)
        self.assertEqual(rows, [])
        self.assertEqual(cfg["partial_errors"], [])  # cleared CF + no data == EMPTY
        self.assertTrue(uc.quit_called)

    def test_multi_term_run_never_reloads_the_page(self):
        # Regression for the 28/07/2026 live break: reloading SOURCE_URL before
        # every search term got the session re-challenged mid-run. The stealth
        # path should only navigate once, up front, to clear the challenge.
        mols = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
                 "fda_term": "regorafenib", "aliases": []},
                {"latam_term": "DAROLUTAMIDA", "ema_term": "darolutamide",
                 "fda_term": "darolutamide", "aliases": ["DAROLUTAMIDE"]}]
        uc = FakeUC(challenge=False, has_box=True)
        cfg = {"partial_errors": [], "pe_stealth": True,
               "uc_driver_factory": lambda h: uc}
        with mock.patch("extractors.pe_approvals.time.sleep"), \
             mock.patch("extractors.selenium_base.wait_for_table", return_value=None):
            pe.extract(mols, cfg)
        self.assertEqual(uc.get_calls, 0)
        self.assertEqual(cfg["partial_errors"], [])

    def test_non_stealth_config_uses_legacy_path(self):
        # Without pe_stealth, the factory must NOT be consulted (legacy port flow).
        sentinel = {"called": False}

        def factory(h):
            sentinel["called"] = True
            return FakeUC()
        cfg = {"partial_errors": [], "uc_driver_factory": factory}
        with mock.patch("extractors.pe_approvals._port_open", return_value=False), \
             mock.patch("extractors.pe_approvals._find_chrome", return_value=None):
            pe.extract(MOL, cfg)
        self.assertFalse(sentinel["called"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
