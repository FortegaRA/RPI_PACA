"""
Colombia submissions — Socrata historical extractor (no network).

co_submissions joins the approvals dataset (i7cb-raxc: expediente -> principio
activo/producto) with the radicados dataset (t2gj-yg8s: trámites) to emit SUBMISSION
rows for the target molecules. These tests pin the join + mapping with a fake
session that answers each dataset by URL.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
import normalize  # noqa: E402
from extractors import co_submissions as cs  # noqa: E402

MOL = [{"latam_term": "DAPAGLIFLOZINA", "ema_term": "dapagliflozin",
        "fda_term": "dapagliflozin", "aliases": []}]

APPROVALS = [
    {"expediente": "20243027", "principioactivo": "DAPAGLIFLOZINA",
     "producto": "FORXIGA 10 MG", "titular": "ASTRAZENECA"},
    {"expediente": "20255614", "principioactivo": "DAPAGLIFLOZINA",
     "producto": "XIGDUO XR", "titular": "ASTRAZENECA"},
]
RADICADOS = {
    "20243027": [
        {"radicado": "2024001", "expediente": "20243027",
         "fecha_inicio_tramite": "2024-03-01T00:00:00.000",
         "tramite": "MODIFICACION DE R.S.", "estado_tramite": "Finalizado"},
        {"radicado": "2024002", "expediente": "20243027",
         "fecha_inicio_tramite": "2024-05-01T00:00:00.000",
         "tramite": "RENOVACION", "estado_tramite": "En proceso"},
    ],
    "20255614": [
        {"radicado": "2024003", "expediente": "20255614",
         "fecha_inicio_tramite": "2024-04-01T00:00:00.000",
         "tramite": "REGISTRO SANITARIO NUEVO", "estado_tramite": "Finalizado"},
    ],
}


def _session(approvals=APPROVALS, radicados=RADICADOS, approvals_exc=None):
    def handler(method, url, **kw):
        where = (kw.get("params") or {}).get("$where", "")
        if "i7cb-raxc" in url:  # approvals lookup
            if approvals_exc:
                raise approvals_exc
            return fk.FakeResponse(json_data=approvals)
        if "t2gj-yg8s" in url:  # radicados
            out = []
            for exp, rads in radicados.items():
                if f"expediente='{exp}'" in where:
                    out.extend(rads)
            return fk.FakeResponse(json_data=out)
        return fk.FakeResponse(json_data=[])
    return fk.FakeSession(handler=handler)


class TestColombiaSubmissions(unittest.TestCase):
    def test_join_produces_enriched_submissions(self):
        c = {"partial_errors": [], "session": _session()}
        rows = cs.extract(MOL, c)
        self.assertEqual(len(rows), 3)  # 2 + 1 radicados
        self.assertEqual(c["partial_errors"], [])
        by_reg = {r["registration_number"]: r for r in rows}
        r = by_reg["2024001"]
        self.assertEqual(r["record_type"], "SUBMISSION")
        self.assertEqual(r["molecule_search_term"], "DAPAGLIFLOZINA")
        self.assertEqual(r["product_name"], "FORXIGA 10 MG")          # joined
        self.assertEqual(r["api"], "DAPAGLIFLOZINA")                   # joined
        self.assertEqual(r["applicant"], "ASTRAZENECA")               # joined titular
        self.assertEqual(r["process_type"], "MODIFICACION DE R.S.")
        self.assertEqual(r["submission_date"], "2024-03-01T00:00:00.000")
        self.assertEqual(r["country_code"], "CO")

    def test_no_expedientes_is_clean_empty(self):
        c = {"partial_errors": [], "session": _session(approvals=[])}
        self.assertEqual(cs.extract(MOL, c), [])
        self.assertEqual(c["partial_errors"], [])

    def test_no_radicados_is_clean_empty(self):
        c = {"partial_errors": [], "session": _session(radicados={})}
        rows = cs.extract(MOL, c)
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_approvals_error_is_recorded(self):
        c = {"partial_errors": [], "session": _session(approvals_exc=fk.FakeConnError("boom"))}
        cs.extract(MOL, c)
        self.assertTrue(any("approvals lookup" in e for e in c["partial_errors"]))

    def test_estado_tramite_values_are_mapped(self):
        # RADICADOS carries "Finalizado" / "En proceso" — both must map to a
        # canonical status, not fall through to normalize's unmapped-status log.
        c = {"partial_errors": [], "session": _session()}
        rows = cs.extract(MOL, c)
        by_reg = {r["registration_number"]: r for r in rows}
        self.assertEqual(normalize.normalize_status(by_reg["2024001"]["status"]), "APPROVED")
        self.assertEqual(normalize.normalize_status(by_reg["2024002"]["status"]), "PENDING")

    def test_en_curso_variant_maps_to_pending(self):
        self.assertEqual(normalize.normalize_status("En Curso"), "PENDING")
        self.assertEqual(normalize.normalize_status("En curso"), "PENDING")

    def test_finalizado_maps_to_approved(self):
        self.assertEqual(normalize.normalize_status("Finalizado"), "APPROVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
