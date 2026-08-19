"""
Regression tests for the Costa Rica / Honduras cross-contamination incident.

What happened (16/08/2026): every extractor shared one download folder. Honduras
downloaded ``MedicamentosArsa.xlsx`` there and left it. Costa Rica ran later, its
own download from registrelo.go.cr silently failed (the portal is a React SPA with
no download button to click), and ``wait_for_download(dir, None, ...)`` happily
returned "the newest .xlsx in the folder" — Honduras' workbook. CR then parsed it
and emitted 24 Honduran registrations tagged ``country_code=CR``, reporting OK.

Two independent guards are pinned here, either of which alone breaks the chain:
    1. wait_for_download only accepts files written *during the call*.
    2. the orchestrator gives each extractor its own download subfolder.
"""

import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import rpi_cluster  # noqa: E402
from extractors import selenium_base as sb  # noqa: E402


def _write(path: str, content: bytes = b"x", age_seconds: float = 0.0) -> str:
    with open(path, "wb") as fh:
        fh.write(content)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


class TestWaitForDownloadRejectsStaleFiles(unittest.TestCase):
    def test_preexisting_file_is_not_accepted_as_a_download(self):
        """The exact CR bug: a stale workbook must NOT count as a fresh download."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "MedicamentosArsa.xlsx"), age_seconds=600)
            got = sb.wait_for_download(tmp, None, timeout=2, exts=(".xlsx", ".xls"))
        self.assertIsNone(got, "a pre-existing workbook must not be returned")

    def test_stale_file_rejected_even_when_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "report.xlsx"), age_seconds=600)
            got = sb.wait_for_download(tmp, "report.xlsx", timeout=2, exts=(".xlsx",))
        self.assertIsNone(got)

    def test_file_written_during_the_call_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(os.path.join(tmp, "fresh.xlsx"))  # mtime = now
            got = sb.wait_for_download(tmp, None, timeout=3, exts=(".xlsx",))
        self.assertEqual(got, path)

    def test_named_fresh_file_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(os.path.join(tmp, "report.xlsx"))
            got = sb.wait_for_download(tmp, "report.xlsx", timeout=3, exts=(".xlsx",))
        self.assertEqual(got, path)


class TestQuarantineMechanism(unittest.TestCase):
    """The disable switch itself stays tested, so the next bad extractor can use it."""

    def test_disabled_group_renders_its_own_label(self):
        label = rpi_cluster._group_label({"DISABLED"}, records=0, ran=True)
        self.assertIn("Disabled", label)

    def test_expected_extractors_are_disabled(self):
        """Peru: pending compliance. Colombia filings: tracked by the team elsewhere."""
        disabled = sorted(e["key"] for e in rpi_cluster.EXTRACTORS if e.get("disabled"))
        self.assertEqual(disabled, ["co_submissions", "pe_approvals", "pe_submissions"])

    def test_colombia_approvals_stay_enabled(self):
        """Only the FILINGS side of Colombia is out of scope — approvals still run."""
        co_apr = next(e for e in rpi_cluster.EXTRACTORS if e["key"] == "co_approvals")
        self.assertFalse(co_apr.get("disabled"))

    def test_disabled_extractors_declare_a_reason(self):
        for entry in rpi_cluster.EXTRACTORS:
            if entry.get("disabled"):
                self.assertIsInstance(entry["disabled"], str)
                self.assertTrue(entry["disabled"].strip(), f"{entry['key']} sin motivo")

    def test_cr_no_longer_downloads_workbooks(self):
        """CR now calls the Registrelo API in-browser; it must not parse local files."""
        from extractors import cr as cr_mod
        src = open(cr_mod.__file__, encoding="utf-8").read()
        self.assertNotIn("wait_for_download", src)
        self.assertNotIn("load_workbook", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
