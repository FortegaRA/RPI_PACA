"""
Per-HA empty-vs-error trigger for the HTTP extractors (no network).

For every HA we assert BOTH:
    * no record for the molecule  -> extract() returns []  and records NO error
    * a fetch failure             -> extract() records a partial_error

Covered here: EMA, FDA, Colombia approvals, El Salvador, Ecuador.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
from extractors import ema, fda, co_approvals, sv  # noqa: E402

MOL = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
        "fda_term": "regorafenib", "aliases": []}]


def cfg(**extra):
    c = {"partial_errors": []}
    c.update(extra)
    return c


# ── EMA (XLSX "Medicine" output) ──────────────────────────────────────────────
# EMA's columns, in order, with a banner row above the header (as the real file).
_EMA_HEADERS = ["Category", "Name of medicine", "EMA product number", "Medicine status",
                "Opinion status", "International non-proprietary name (INN) / common name",
                "Active substance", "Therapeutic area (MeSH)", "Therapeutic indication",
                "Biosimilar", "Marketing authorisation developer / applicant / holder",
                "European Commission decision date", "Opinion adopted date",
                "Start of evaluation date", "Marketing authorisation date",
                "Withdrawal / expiry / revocation / lapse of marketing authorisation date",
                "Medicine URL"]


def _ema_xlsx(rows):
    """Build an in-memory EMA-style XLSX (banner row + header + data) as bytes.

    Each row in *rows* is a dict keyed by header label; missing keys are blank.
    """
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Content type:", "Medicine", "Output generated on:", "22/06/2026"])  # banner
    ws.append(_EMA_HEADERS)
    for r in rows:
        ws.append([r.get(h, "") for h in _EMA_HEADERS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ema_session(rows):
    content = _ema_xlsx(rows)
    return fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(content=content))


class TestEMA(unittest.TestCase):
    def test_no_record_empty(self):
        # A valid sheet with no data rows -> no molecule matches, clean empty.
        c = cfg(session=_ema_session([]))
        rows = ema.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_no_record_empty_even_with_unrelated_data(self):
        # The report has records, just none for our molecules -> still a clean empty.
        unrelated = [{"Category": "Human", "EMA product number": "EMEA/H/C/1",
                      "Active substance": "paracetamol", "Name of medicine": "Panadol",
                      "Medicine status": "Authorised"}]
        c = cfg(session=_ema_session(unrelated))
        self.assertEqual(ema.extract(MOL, c), [])
        self.assertEqual(c["partial_errors"], [])

    def test_fetch_failure_records_error(self):
        sess = fk.FakeSession(raise_exc=fk.FakeConnError("getaddrinfo failed"))
        c = cfg(session=sess)
        rows = ema.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "EMA must record an error on fetch failure")

    def test_real_record_is_found_as_approval(self):
        match = [{"Category": "Human", "EMA product number": "EMEA/H/C/9",
                  "Active substance": "regorafenib",
                  "International non-proprietary name (INN) / common name": "regorafenib",
                  "Name of medicine": "Stivarga", "Medicine status": "Authorised",
                  "Marketing authorisation date": "26/08/2013"}]
        c = cfg(session=_ema_session(match))
        rows = ema.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_type"], "APPROVAL")  # has a MA date
        self.assertEqual(rows[0]["registration_number"], "EMEA/H/C/9")
        self.assertEqual(c["partial_errors"], [])

    def test_in_evaluation_is_submission(self):
        # No marketing-authorisation date -> still under evaluation -> SUBMISSION.
        match = [{"Category": "Human", "EMA product number": "EMEA/H/C/77",
                  "International non-proprietary name (INN) / common name": "regorafenib",
                  "Name of medicine": "Newdrug", "Medicine status": "Opinion",
                  "Opinion adopted date": "27/06/2026"}]
        rows = ema.extract(MOL, cfg(session=_ema_session(match)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_type"], "SUBMISSION")

    def test_veterinary_rows_are_skipped(self):
        match = [{"Category": "Veterinary", "EMA product number": "EMEA/V/C/1",
                  "International non-proprietary name (INN) / common name": "regorafenib",
                  "Name of medicine": "VetReg", "Medicine status": "Authorised",
                  "Marketing authorisation date": "01/01/2020"}]
        rows = ema.extract(MOL, cfg(session=_ema_session(match)))
        self.assertEqual(rows, [])


# ── FDA ───────────────────────────────────────────────────────────────────────
class TestFDA(unittest.TestCase):
    def test_no_record_empty_on_404(self):
        # OpenFDA returns 404 when a search has no matches -> a real "no record".
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(status_code=404))
        c = cfg(session=sess)
        rows = fda.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_fetch_failure_records_error(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(status_code=500))
        c = cfg(session=sess)
        rows = fda.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "FDA must record an error on HTTP 500")

    def test_connection_error_records_error(self):
        sess = fk.FakeSession(raise_exc=fk.FakeConnError("connection reset"))
        c = cfg(session=sess)
        fda.extract(MOL, c)
        self.assertTrue(c["partial_errors"])


# ── Colombia approvals ────────────────────────────────────────────────────────
class TestColombiaApprovals(unittest.TestCase):
    def test_no_record_empty(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=[]))
        c = cfg(session=sess)
        rows = co_approvals.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_fetch_failure_records_error(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(status_code=503))
        c = cfg(session=sess)
        co_approvals.extract(MOL, c)
        self.assertTrue(c["partial_errors"], "CO approvals must record an error on HTTP 503")

    def test_us_date_fields_converted_to_iso(self):
        # Socrata returns fechaexpedicion/fechavencimiento as MM/DD/YYYY. "06/09/2026"
        # is 9 June (not 6 September) — day-first parsing would silently swap it.
        rec = [{"registrosanitario": "INVIMA2026M-1", "principioactivo": "REGORAFENIB",
                "producto": "STIVARGA", "fechaexpedicion": "06/09/2026",
                "fechavencimiento": "12/30/2031"}]
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=rec))
        rows = co_approvals.extract(MOL, cfg(session=sess))
        self.assertEqual(rows[0]["approval_date"], "2026-06-09")   # NOT 2026-09-06
        self.assertEqual(rows[0]["expiration_date"], "2031-12-30")  # NOT invalid month=30

    def test_unparseable_date_passes_through(self):
        rec = [{"registrosanitario": "INVIMA2026M-2", "principioactivo": "REGORAFENIB",
                "fechaexpedicion": "not-a-date"}]
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=rec))
        rows = co_approvals.extract(MOL, cfg(session=sess))
        self.assertEqual(rows[0]["approval_date"], "not-a-date")


# ── El Salvador (DataTables JSON endpoint) ────────────────────────────────────
class TestElSalvador(unittest.TestCase):
    def test_no_record_empty(self):
        # recordsFiltered=0 with an empty data array == no product for this molecule.
        payload = {"draw": 1, "recordsTotal": 0, "recordsFiltered": 0, "data": []}
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=payload))
        c = cfg(session=sess)
        rows = sv.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_fetch_failure_records_error(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(status_code=500))
        c = cfg(session=sess)
        sv.extract(MOL, c)
        self.assertTrue(c["partial_errors"], "SV must record an error on HTTP 500")

    def test_real_record_is_found(self):
        rec = {"registroSanitario": "F12345", "nombreRegistro": "DAPAONE",
               "titular": "ACME", "estado": "ACTIVO", "primeraAutorizacion": "2023-01-01"}
        page = {"recordsFiltered": 1, "data": [rec]}
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=page))
        c = cfg(session=sess)
        rows = sv.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(c["partial_errors"], [])


# Ecuador is covered by tests/test_ecuador.py (bulk-report model).


# ── FDA: one row per product, combos preserved (anti-undercount fix) ──────────
class TestFDAProductExpansion(unittest.TestCase):
    def _result(self):
        return {
            "results": [{
                "application_number": "NDA200001",
                "sponsor_name": "ACME",
                "submissions": [{"submission_status": "AP",
                                 "submission_status_date": "20230115",
                                 "submission_type": "ORIG"}],
                "products": [
                    {"product_number": "001", "brand_name": "MONO 10",
                     "dosage_form": "TABLET",
                     "active_ingredients": [{"name": "DAPAGLIFLOZIN", "strength": "10MG"}]},
                    {"product_number": "002", "brand_name": "COMBO XR",
                     "dosage_form": "TABLET",
                     "active_ingredients": [{"name": "DAPAGLIFLOZIN", "strength": "5MG"},
                                            {"name": "METFORMIN", "strength": "1000MG"}]},
                ],
            }]
        }

    def test_emits_one_row_per_product_with_unique_pk(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=self._result()))
        c = cfg(session=sess)
        rows = fda.extract(MOL, c)
        self.assertEqual(len(rows), 2)  # two products, not one collapsed row
        pks = {r["registration_number"] for r in rows}
        self.assertEqual(pks, {"NDA200001-001", "NDA200001-002"})  # unique per presentation
        self.assertEqual(c["partial_errors"], [])

    def test_combo_api_lists_all_ingredients(self):
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=self._result()))
        rows = fda.extract(MOL, cfg(session=sess))
        combo = next(r for r in rows if r["registration_number"] == "NDA200001-002")
        self.assertEqual(combo["api"], "DAPAGLIFLOZIN + METFORMIN")  # not collapsed to [0]
        self.assertEqual(combo["concentration"], "5MG + 1000MG")

    def test_single_product_keeps_bare_application_pk(self):
        one = {"results": [{
            "application_number": "NDA999",
            "submissions": [{"submission_status": "AP", "submission_status_date": "20220101"}],
            "products": [{"product_number": "001", "brand_name": "SOLO",
                          "active_ingredients": [{"name": "REGORAFENIB", "strength": "40MG"}]}],
        }]}
        sess = fk.FakeSession(handler=lambda m, u, **k: fk.FakeResponse(json_data=one))
        rows = fda.extract(MOL, cfg(session=sess))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["registration_number"], "NDA999")  # no -001 suffix


# ── Colombia approvals: substring match + pagination (anti-undercount fix) ────
class TestColombiaContainsAndPaging(unittest.TestCase):
    def test_where_uses_contains_not_prefix(self):
        captured = {}

        def handler(method, url, **kw):
            captured["where"] = (kw.get("params") or {}).get("$where", "")
            return fk.FakeResponse(json_data=[])

        co_approvals.extract(MOL, cfg(session=fk.FakeSession(handler=handler)))
        # leading + trailing % so salt-prefixed / combo / free-text rows are caught
        self.assertIn("like '%REGORAFENIB%'", captured["where"])

    def test_paginates_until_short_page(self):
        page = co_approvals._PAGE
        full = [{"registrosanitario": f"R{i}", "principioactivo": "REGORAFENIB"}
                for i in range(page)]
        tail = [{"registrosanitario": "RTAIL", "principioactivo": "REGORAFENIB"}]

        def handler(method, url, **kw):
            off = int((kw.get("params") or {}).get("$offset", 0))
            return fk.FakeResponse(json_data=full if off == 0 else tail)

        rows = co_approvals.extract(MOL, cfg(session=fk.FakeSession(handler=handler)))
        # page + 1 distinct registros across two pages -> no silent truncation
        self.assertEqual(len(rows), page + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestColombiaDistinguishesOutageFromEmpty(unittest.TestCase):
    """An empty SOURCE must not be reported as "no registrations exist".

    Socrata answers both cases with HTTP 200 + []. Reporting a publishing outage as
    a clean EMPTY would let someone conclude "no competitor product is registered in
    Colombia" when in truth nobody could see the data. Observed live on 18/08/2026,
    when INVIMA republished every CUM dataset with 0 rows.
    """

    def _session(self, dataset_count, molecule_rows):
        def handler(method, url, **kw):
            params = kw.get("params") or {}
            if params.get("$select") == "count(1) as c":
                return fk.FakeResponse(json_data=[{"c": str(dataset_count)}])
            return fk.FakeResponse(json_data=molecule_rows)
        return fk.FakeSession(handler=handler)

    def test_empty_dataset_is_an_error_not_a_clean_empty(self):
        c = cfg(session=self._session(dataset_count=0, molecule_rows=[]))
        rows = co_approvals.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertTrue(c["partial_errors"], "an empty dataset must surface as FAILED")
        self.assertIn("vacío", c["partial_errors"][0])

    def test_populated_dataset_with_no_match_stays_a_clean_empty(self):
        c = cfg(session=self._session(dataset_count=157184, molecule_rows=[]))
        rows = co_approvals.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [],
                         "a real 'no registration for this molecule' is still EMPTY")

    def test_populated_dataset_with_matches_returns_rows(self):
        rec = [{"registrosanitario": "INVIMA 2025M-1", "principioactivo": "REGORAFENIB",
                "producto": "STIVARGA"}]
        c = cfg(session=self._session(dataset_count=157184, molecule_rows=rec))
        rows = co_approvals.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(c["partial_errors"], [])


class TestElSalvadorFirstClaimWins(unittest.TestCase):
    """A registration belongs to the first molecule that claims it.

    El Salvador is queried once per search term, so a product that answers several
    terms comes back several times. Without a guard, deduplication keeps whichever
    was appended last — and since the Factor VIII class entry sits at the end of the
    panel, it took ESPEROCT away from turoctocog alfa pegol on the live portal.
    """

    TWO = [
        {"inn": "Turoctocog alfa pegol", "latam_term": "TUROCTOCOG ALFA PEGOL",
         "ema_term": "turoctocog alfa pegol", "fda_term": "turoctocog alfa pegol",
         "aliases": []},
        {"inn": "Factor VIII (clase)", "latam_term": "FACTOR VIII",
         "ema_term": "coagulation factor viii", "fda_term": "antihemophilic factor",
         "aliases": []},
    ]

    def _session(self, *, both_terms_return_esperoct=True):
        rec = {"registroSanitario": "SV-ESPEROCT-1", "nombreRegistro": "Esperoct 500 UI",
               "titular": "NOVO", "estado": "ACTIVO", "primeraAutorizacion": "2024-01-01"}
        def handler(method, url, **kw):
            term = (kw.get("params") or {}).get("busqueda", "")
            hit = both_terms_return_esperoct or term.startswith("TUROCTOCOG")
            data = [rec] if hit else []
            return fk.FakeResponse(json_data={"recordsFiltered": len(data), "data": data})
        return fk.FakeSession(handler=handler)

    def test_specific_molecule_keeps_the_row(self):
        c = cfg(session=self._session())
        rows = sv.extract(self.TWO, c)
        self.assertEqual(len(rows), 1, "the product must not be emitted twice")
        self.assertEqual(rows[0]["molecule_search_term"], "TUROCTOCOG ALFA PEGOL")

    def test_class_entry_still_collects_what_is_left(self):
        """Reversing the order proves the guard is about position, not identity."""
        c = cfg(session=self._session())
        rows = sv.extract(list(reversed(self.TWO)), c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["molecule_search_term"], "FACTOR VIII")

    def test_distinct_registrations_are_all_kept(self):
        def handler(method, url, **kw):
            term = (kw.get("params") or {}).get("busqueda", "")
            rec = {"registroSanitario": f"SV-{term[:6]}", "nombreRegistro": f"P {term[:6]}",
                   "titular": "X", "estado": "ACTIVO", "primeraAutorizacion": "2024-01-01"}
            return fk.FakeResponse(json_data={"recordsFiltered": 1, "data": [rec]})
        rows = sv.extract(self.TWO, cfg(session=fk.FakeSession(handler=handler)))
        self.assertEqual(len({r["registration_number"] for r in rows}), 2)
