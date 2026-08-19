"""
The heart of the empty-vs-error distinction: rpi_cluster.run_extractor must turn an
extractor's (rows, partial_errors) into the right status, and the run summary must
render distinct labels.

    rows  errors  -> status            summary label
    ----  ------     ------            -------------
     []     []        EMPTY            "Empty"   (genuinely no record)
     []     yes       FAILED           "Failed"  (extraction broke)
     yes    []        OK               "OK"
     yes    yes       PARTIAL          "Partial" (some molecules broke)
     (raise)          ERROR            "Error"   (unhandled)
"""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import rpi_cluster  # noqa: E402

ENTRY = {"key": "ema", "label": "EMA", "group": "EMA (EU)",
         "module": "extractors.ema", "outfile": "RPIEMA_canonical.csv", "selenium": False}
MOLS = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
         "fda_term": "regorafenib", "aliases": []}]


def _run(extract_fn):
    """Run run_extractor with a stubbed extractor module in a throwaway dir."""
    mod = types.SimpleNamespace(extract=extract_fn)
    with tempfile.TemporaryDirectory() as tmp:
        ex_config = {"output_dir": tmp, "download_dir": tmp, "partial_errors": [],
                     "country_code": "EU", "source_url": "http://x", "record_type": None}
        with mock.patch.object(rpi_cluster.importlib, "import_module", return_value=mod):
            return rpi_cluster.run_extractor(ENTRY, MOLS, ex_config, tmp)


def _row():
    return {"registration_number": "R1", "country_code": "EU", "record_type": "APPROVAL"}


class TestStatusClassification(unittest.TestCase):
    def test_no_record_is_empty_not_error(self):
        """The key case: 0 rows + no errors => EMPTY (a real 'no record'), 0 approvals."""
        res = _run(lambda mols, cfg: [])
        self.assertEqual(res["status"], "EMPTY")
        self.assertEqual(res["approvals"], 0)
        self.assertEqual(res["submissions"], 0)

    def test_failure_with_no_rows_is_failed_not_empty(self):
        """0 rows but an error recorded => FAILED, clearly distinct from EMPTY."""
        def extract(mols, cfg):
            cfg["partial_errors"].append("EMA: fetch failed for medicines.json")
            return []
        res = _run(extract)
        self.assertEqual(res["status"], "FAILED")

    def test_rows_no_errors_is_ok(self):
        res = _run(lambda mols, cfg: [_row()])
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["approvals"], 1)

    def test_rows_with_some_errors_is_partial(self):
        def extract(mols, cfg):
            cfg["partial_errors"].append("EMA: one molecule timed out")
            return [_row()]
        res = _run(extract)
        self.assertEqual(res["status"], "PARTIAL")
        self.assertEqual(res["approvals"], 1)

    def test_unhandled_exception_is_error(self):
        def extract(mols, cfg):
            raise RuntimeError("boom")
        res = _run(extract)
        self.assertEqual(res["status"], "ERROR")


class TestSummaryLabels(unittest.TestCase):
    """The five statuses must map to visually distinct summary labels."""

    def _label(self, statuses, records, ran=True):
        return rpi_cluster._group_label(set(statuses), records, ran)

    def test_empty_label_distinct_from_failed(self):
        empty = self._label({"EMPTY"}, 0)
        failed = self._label({"FAILED"}, 0)
        self.assertIn("Empty", empty)
        self.assertIn("Failed", failed)
        self.assertNotEqual(empty, failed)

    def test_ok_partial_error_skipped_notrun(self):
        self.assertIn("OK", self._label({"OK"}, 5))
        self.assertIn("Partial", self._label({"PARTIAL"}, 5))
        self.assertIn("Error", self._label({"ERROR"}, 0))
        self.assertIn("Skipped", self._label({"SKIPPED"}, 0))
        self.assertIn("not run", self._label(set(), 0, ran=False))

    def test_error_dominates_mixed_group(self):
        # A country whose two extractors are one OK + one ERROR must surface ERROR.
        self.assertIn("Error", self._label({"OK", "ERROR"}, 5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
