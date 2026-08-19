"""
Per-HA empty-vs-error trigger for Honduras (bulk Excel download + parse).

    * downloaded workbook with no target molecule -> []  and NO error  (EMPTY)
    * download fails and Selenium fallback disabled -> records an error  (FAILED)
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
import config  # noqa: E402
from extractors import hn  # noqa: E402

MOL = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
        "fda_term": "regorafenib", "aliases": []}]

# Real ARSA headers carry trailing colons; the sheet is named "Registros".
HN_HEADERS = [
    "No. ", "Tipo de solicitud:", "Nombre del producto:",
    "Nombre de sustancias activas / Principio activo:", "Forma farmacéutica:",
    "Concentracion por unidad de dosis:", "Nombre del fabricante:",
    "Pais del Fabricante ", "Nombre del titular", "Numero de Registro Sanitario",
]


def _make_hn_xlsx(path, substance, product="ALGUN PRODUCTO"):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Registros"
    ws.append(HN_HEADERS)
    ws.append(["1", "Inscripcion", product, substance, "TABLETA",
               "100 MG", "LAB FAB", "INDIA", "TITULAR SA", "HN-M-0001-0001"])
    wb.save(path)


class TestHonduras(unittest.TestCase):
    def test_no_record_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            xlsx = os.path.join(tmp, "hn_fixture.xlsx")  # not EXPECTED_FILE -> not purged
            _make_hn_xlsx(xlsx, substance="LORATADINA")  # not a target molecule
            with mock.patch("extractors.hn._download_direct", return_value=xlsx), \
                 mock.patch("extractors.selenium_base.clear_downloads"):
                c = {"partial_errors": [], "download_dir": tmp}
                rows = hn.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_real_record_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            xlsx = os.path.join(tmp, "hn_fixture.xlsx")
            _make_hn_xlsx(xlsx, substance="REGORAFENIB")
            with mock.patch("extractors.hn._download_direct", return_value=xlsx), \
                 mock.patch("extractors.selenium_base.clear_downloads"):
                c = {"partial_errors": [], "download_dir": tmp}
                rows = hn.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["registration_number"], "HN-M-0001-0001")
        self.assertEqual(c["partial_errors"], [])

    def test_download_failure_records_error(self):
        # Direct HTTP download fails; Selenium fallback disabled (--no-selenium).
        sess = fk.FakeSession(raise_exc=fk.FakeConnError("getaddrinfo failed"))
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(config, "build_session", return_value=sess), \
             mock.patch("extractors.hn.time.sleep"):
            c = {"partial_errors": [], "download_dir": tmp, "no_selenium": True}
            rows = hn.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "HN must record an error when the download fails")


if __name__ == "__main__":
    unittest.main(verbosity=2)
