"""
Alias search (#1): LATAM extractors must also try a molecule's INN-variant aliases,
so a product registered under a different spelling than the LATAM term is not lost.

Motivating case: Tadalafil's LATAM term is "TADAFILO", but it is registered as
"TADALAFILO". Rows found via an alias must still be tagged with the canonical
latam_term so reporting stays grouped, and broad class aliases (e.g. "FACTOR VIII")
must NOT be expanded.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
import config  # noqa: E402
from extractors import sv, co_approvals  # noqa: E402

# Tadalafil exactly as config has it (LATAM term differs from the real spelling).
TADALAFIL = {"latam_term": "TADAFILO", "ema_term": "tadalafil", "fda_term": "tadalafil",
             "aliases": ["TADALAFIL", "TADALAFILO"]}


class TestSearchTerms(unittest.TestCase):
    def test_includes_inn_variants(self):
        self.assertEqual(config.search_terms(TADALAFIL), ["TADAFILO", "TADALAFIL", "TADALAFILO"])

    def test_excludes_broad_terms(self):
        """A mechanism-level alias would mislabel every product of its class."""
        marstacimab = {"latam_term": "MARSTACIMAB", "aliases": ["MARSTICIMAB", "ANTI-TFPI"]}
        terms = config.search_terms(marstacimab)
        self.assertIn("MARSTICIMAB", terms)
        self.assertNotIn("ANTI-TFPI", terms)  # broad -> not expanded

    def test_factor_viii_is_no_longer_broad(self):
        """It stopped being a stray alias and became the class entry's own term.

        As an alias on turoctocog it grabbed the whole hemophilia-A market; as the
        `latam_term` of an entry placed last in MOLECULES it only picks up what the
        specific molecules did not already claim.
        """
        clase = next(m for m in config.MOLECULES if m["inn"] == "Factor VIII (clase)")
        self.assertIn("FACTOR VIII", config.search_terms(clase))

    def test_deduplicates_and_uppercases(self):
        m = {"latam_term": "foo", "aliases": ["FOO", "foo", "Bar"]}
        self.assertEqual(config.search_terms(m), ["FOO", "BAR"])


class TestSVAliasExpansion(unittest.TestCase):
    def test_finds_via_alias_tagged_with_canonical_term(self):
        # The fake portal only has data under the alias "TADALAFILO".
        def handler(method, url, **kw):
            busqueda = (kw.get("params") or {}).get("busqueda", "")
            if busqueda == "TADALAFILO":
                rec = {"registroSanitario": "F999", "nombreRegistro": "TADALAFILO 20 MG",
                       "titular": "ACME", "estado": "ACTIVO", "primeraAutorizacion": "2024-01-01"}
                return fk.FakeResponse(json_data={"recordsFiltered": 1, "data": [rec]})
            return fk.FakeResponse(json_data={"recordsFiltered": 0, "data": []})

        c = {"partial_errors": [], "session": fk.FakeSession(handler=handler)}
        rows = sv.extract([TADALAFIL], c)
        self.assertEqual(len(rows), 1, "SV should find tadalafil via the TADALAFILO alias")
        self.assertEqual(rows[0]["molecule_search_term"], "TADAFILO",
                         "row must be tagged with the canonical latam_term")
        self.assertEqual(c["partial_errors"], [])

    def test_latam_term_only_would_have_missed_it(self):
        # Control: searching only the LATAM term returns nothing.
        def handler(method, url, **kw):
            busqueda = (kw.get("params") or {}).get("busqueda", "")
            data = [] if busqueda != "TADALAFILO" else [{"registroSanitario": "F1"}]
            return fk.FakeResponse(json_data={"recordsFiltered": len(data), "data": data})

        c = {"partial_errors": [], "session": fk.FakeSession(handler=handler)}
        only_latam = {"latam_term": "TADAFILO", "ema_term": "tadalafil",
                      "fda_term": "tadalafil", "aliases": []}
        self.assertEqual(sv.extract([only_latam], c), [])  # missed without aliases


class TestCOAliasExpansion(unittest.TestCase):
    def test_finds_via_alias_tagged_with_canonical_term(self):
        def handler(method, url, **kw):
            where = (kw.get("params") or {}).get("$where", "")
            if "TADALAFILO" in where:
                return fk.FakeResponse(json_data=[{
                    "registrosanitario": "INVIMA-TAD", "principioactivo": "TADALAFILO",
                    "producto": "ADCIRCA", "titular": "ACME",
                    "descripcionatc": "hipertension arterial pulmonar"}])
            return fk.FakeResponse(json_data=[])

        c = {"partial_errors": [], "session": fk.FakeSession(handler=handler)}
        rows = co_approvals.extract([TADALAFIL], c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["molecule_search_term"], "TADAFILO")
        # The ATC description rode along as the post-filter hint.
        self.assertIn("pulmonar", (rows[0].get("_indication_hint") or "").lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
