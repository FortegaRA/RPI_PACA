"""
Per-HA empty-vs-error trigger for the Selenium extractors (no real Chrome).

The driver is faked. The "no record" case is simulated by letting the search
succeed but the results table come back empty; the "error" case is simulated by
making navigation raise (network/portal failure). For each HA we assert:

    * no record -> extract() returns []  and records NO partial_error
    * failure   -> extract() records a partial_error

Covered: Guatemala, Dominican Republic, Costa Rica, Peru approvals,
Peru submissions, Colombia submissions.
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
from extractors import gt, do, cr, pe_approvals, pe_submissions  # noqa: E402

MOL = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
        "fda_term": "regorafenib", "aliases": []}]
NET_DOWN = fk.FakeWebDriverException("unknown error: net::ERR_NAME_NOT_RESOLVED")


def cfg(**extra):
    c = {"partial_errors": [], "headless": True, "non_interactive": True}
    c.update(extra)
    return c


def _make_cr_xlsx(path, product):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["numero_registro", "nombre_producto", "solicitante", "estado", "tipo_expediente"])
    ws.append(["CR-1", product, "ACME LAB", "vigente", "Registro"])
    wb.save(path)


# ── Guatemala ─────────────────────────────────────────────────────────────────
class TestGuatemala(unittest.TestCase):
    def test_no_record_empty(self):
        fake = fk.FakeDriver()
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.selenium_base.wait_for_table", return_value=object()), \
             mock.patch("extractors.selenium_base.find_data_table", return_value=(None, {})), \
             mock.patch("extractors.gt.time.sleep"):
            c = cfg()
            rows = gt.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])
        self.assertTrue(fake.quit_called)

    def test_navigation_failure_records_error(self):
        fake = fk.FakeDriver(raise_on_get=NET_DOWN)
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.gt.time.sleep"):
            c = cfg()
            rows = gt.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "GT must record an error when navigation fails")


# ── Dominican Republic ────────────────────────────────────────────────────────
class TestDominicanRepublic(unittest.TestCase):
    def test_no_record_empty(self):
        fake = fk.FakeDriver()
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.selenium_base.wait_for_table", return_value=None), \
             mock.patch("extractors.do.time.sleep"):
            c = cfg()
            rows = do.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_navigation_failure_records_error(self):
        fake = fk.FakeDriver(raise_on_get=NET_DOWN)
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.do.time.sleep"):
            c = cfg()
            do.extract(MOL, c)
        self.assertTrue(c["partial_errors"], "DO must record an error when navigation fails")


# ── Costa Rica (Registrelo public report API, driven in-browser) ──────────────
# The driver is faked: `execute_async_script` answers each report code from a dict,
# standing in for the reCAPTCHA-gated gateway call.
class _CRDriver(fk.FakeDriver):
    def __init__(self, responses: dict, **kw):
        super().__init__(**kw)
        self.responses = responses
        self.calls: list = []

    def set_script_timeout(self, t):
        pass

    def execute_script(self, script, *a):
        if "grecaptcha" in str(script):
            return True          # reCAPTCHA present
        return "complete"        # document.readyState

    def execute_async_script(self, script, *args):
        code, params = args[0], args[1]
        self.calls.append((code, params))
        payload = self.responses.get(code)
        if callable(payload):
            payload = payload(params)
        if payload is None:
            return {"ok": False, "status": 500, "data": [], "message": "boom"}
        return {"ok": True, "status": 200, "data": payload, "message": "ok"}


def _cr_cfg(**extra):
    c = cfg(**extra)
    c["download_dir"] = c.get("download_dir") or "."
    return c


class TestCostaRica(unittest.TestCase):
    def test_no_record_empty(self):
        # The registry responds, but holds no product for our molecule.
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [{"productName": "IBUPRAX 400",
                                  "activeIngredient": "IBUPROFENO"}],
            cr.RPT_PROCEDURES: [],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            c = _cr_cfg()
            rows = cr.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [], "no match is EMPTY, not an error")

    def test_api_failure_records_error(self):
        drv = _CRDriver({cr.RPT_INGREDIENTS: None})  # gateway 500
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            c = _cr_cfg()
            rows = cr.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "CR must record an error when the API fails")

    def test_brand_named_product_is_found_via_ingredient_join(self):
        """The core fix: a brand name carrying no INN must still be found."""
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [{"productName": "RIOCI® 1,5",
                                  "activeIngredient": "REGORAFENIB"}],
            cr.RPT_PRODUCTS: [{"registerNumber": "M-IN-26-1", "productName": "RIOCI® 1,5",
                               "subTypeName": "Medicamentos", "statusName": "vigente",
                               "createdAt": "2026-07-29T21:48:27.475Z",
                               "expiredAt": "2031-07-29T21:48:27.000Z",
                               "headline": "ACME CR", "manufacturers": "FAB UNO; FAB DOS",
                               "countrySource": "Costa Rica"}],
            cr.RPT_PROCEDURES: [],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            c = _cr_cfg()
            rows = cr.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["registration_number"], "M-IN-26-1")
        self.assertEqual(r["record_type"], "APPROVAL")
        self.assertEqual(r["molecule_search_term"], "REGORAFENIB")
        self.assertEqual(r["api"], "REGORAFENIB")          # joined from report 62
        self.assertEqual(r["manufacturer"], "FAB UNO")     # first of the ';' list
        self.assertEqual(c["partial_errors"], [])

    def test_substring_false_positive_is_rejected(self):
        """'RIOCI' substring-matches 'cRIOCIrugía'; a non-medicine must not survive."""
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [{"productName": "RIOCI", "activeIngredient": "REGORAFENIB"}],
            cr.RPT_PRODUCTS: [{"registerNumber": "EMB-US-17-01848",
                               "productName": "SISTEMA DE CRIOCIRUGIA LL100",
                               "subTypeName": "Equipo y Material Biomédico",
                               "statusName": "vigente"}],
            cr.RPT_PROCEDURES: [],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            c = _cr_cfg()
            rows = cr.extract(MOL, c)
        self.assertEqual(rows, [], "a biomedical device must never be emitted as a medicine")

    def test_procedures_become_submissions(self):
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [],
            cr.RPT_PROCEDURES: [{"procedureCode": "622679", "requester": "ASTRAZENECA AB",
                                 "manufacturer": "AZ LP; SK Biotek",
                                 "activeIngredient": "REGORAFENIB",
                                 "link": "https://registrelo.go.cr/x/1"}],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            c = _cr_cfg()
            rows = cr.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_type"], "SUBMISSION")
        # Keyed per procedure: código + the adminProcedures id from its link.
        self.assertEqual(rows[0]["registration_number"], "622679-1")
        self.assertEqual(rows[0]["applicant"], "ASTRAZENECA AB")
        self.assertIsNone(rows[0]["submission_date"], "report 64 has no date — must stay NULL")

    def test_never_emits_a_non_cr_country_code(self):
        """Guards the incident: every row must be CR, whatever the source returns."""
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [{"productName": "X", "activeIngredient": "REGORAFENIB"}],
            cr.RPT_PRODUCTS: [{"registerNumber": "HN-M-0723-0046", "productName": "X",
                               "subTypeName": "Medicamentos", "statusName": "vigente"}],
            cr.RPT_PROCEDURES: [],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            rows = cr.extract(MOL, _cr_cfg())
        self.assertTrue(all(r["country_code"] == "CR" for r in rows))


# ── Peru approvals (CAPTCHA / remote-debug) ───────────────────────────────────
class TestPeruApprovals(unittest.TestCase):
    def test_no_record_empty(self):
        fake = fk.FakeDriver()
        with mock.patch("extractors.pe_approvals._port_open", return_value=True), \
             mock.patch("extractors.pe_approvals._debug_browser", return_value="Chrome/124.0.0.0"), \
             mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.pe_approvals._wait_for_captcha"), \
             mock.patch("extractors.pe_approvals._harvest", return_value=[]), \
             mock.patch("extractors.pe_approvals.time.sleep"):
            c = cfg()
            rows = pe_approvals.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_no_chrome_records_error(self):
        # No browser to attach to and no Chrome to launch -> an infrastructure error.
        with mock.patch("extractors.pe_approvals._port_open", return_value=False), \
             mock.patch("extractors.pe_approvals._find_chrome", return_value=None):
            c = cfg()
            rows = pe_approvals.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "PE approvals must record an error with no Chrome")


# ── Peru submissions (CDP stealth / Livewire) ─────────────────────────────────
class TestPeruSubmissions(unittest.TestCase):
    def test_no_record_empty(self):
        fake = fk.FakeDriver()
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.selenium_base.wait_for_table", return_value=None), \
             mock.patch("extractors.pe_submissions.time.sleep"):
            c = cfg()
            rows = pe_submissions.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_navigation_failure_records_error(self):
        fake = fk.FakeDriver(raise_on_get=NET_DOWN)
        with mock.patch("extractors.selenium_base.build_driver", return_value=fake), \
             mock.patch("extractors.pe_submissions.time.sleep"):
            c = cfg()
            pe_submissions.extract(MOL, c)
        self.assertTrue(c["partial_errors"], "PE submissions must record an error on nav failure")

# Colombia submissions is now a Socrata HTTP extractor — see tests/test_co_submissions.py.

if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCostaRicaProcedureKey(unittest.TestCase):
    """A procedure must be identified per procedure, not per código.

    `procedureCode` repeats in the source: MS-2026-37103 comes back twice, under
    adminProcedures 1216905 and 1255047. Keying on the código alone let
    normalize.deduplicate() collapse them — dropping ~20% of Costa Rica's filings,
    and, critically for novelty tracking, swallowing a genuinely new procedure that
    happens to share a código with one already on file.
    """

    def test_key_combines_code_and_procedure_id(self):
        pk = cr._procedure_pk("MS-2026-37103",
                              "https://registrelo.go.cr/funcionarios/adminProcedures/1255047")
        self.assertEqual(pk, "MS-2026-37103-1255047")

    def test_same_code_different_procedure_stays_distinct(self):
        base = "https://registrelo.go.cr/funcionarios/adminProcedures/"
        a = cr._procedure_pk("MS-2026-37103", base + "1216905")
        b = cr._procedure_pk("MS-2026-37103", base + "1255047")
        self.assertNotEqual(a, b, "two procedures must not collapse into one row")

    def test_code_remains_readable_in_the_key(self):
        """The MS-YYYY- prefix is the only filing-year signal this report offers."""
        pk = cr._procedure_pk("MS-2026-37103",
                              "https://registrelo.go.cr/funcionarios/adminProcedures/1255047")
        self.assertTrue(pk.startswith("MS-2026-"))

    def test_missing_link_falls_back_to_the_code(self):
        for link in (None, "", "https://registrelo.go.cr/sin-id"):
            self.assertEqual(cr._procedure_pk("711013", link), "711013")

    def test_two_procedures_survive_end_to_end(self):
        base = "https://registrelo.go.cr/funcionarios/adminProcedures/"
        drv = _CRDriver({
            cr.RPT_INGREDIENTS: [],
            cr.RPT_PROCEDURES: [
                {"procedureCode": "MS-2026-37103", "requester": "BIOPLUS",
                 "activeIngredient": "REGORAFENIB", "link": base + "1216905"},
                {"procedureCode": "MS-2026-37103", "requester": "BIOPLUS",
                 "activeIngredient": "REGORAFENIB", "link": base + "1255047"},
            ],
        })
        with mock.patch("extractors.selenium_base.build_driver", return_value=drv), \
             mock.patch("extractors.cr.time.sleep"):
            rows = cr.extract(MOL, _cr_cfg())
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["registration_number"] for r in rows}), 2)
