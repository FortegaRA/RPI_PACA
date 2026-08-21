"""
Guatemala is searched by product, and every row still names its molecule.

MSPAS serves its *Principio Activo* column empty, so querying an INN only finds the
generics that carry it in their name: "ENZALUTAMIDA Lotus 40mg" turns up, IZABAN and
YESAFILI do not. The Guatemala PO supplies the brands actually marketed there, and
each one is paired with its molecule — that pairing is what lets a Guatemalan brand
consolidate with the same molecule in the other countries.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import config  # noqa: E402
import normalize  # noqa: E402


class TestProductList(unittest.TestCase):
    def test_brands_map_to_a_molecule(self):
        by_term = {t: inn for inn, terms in config.GT_SEARCH_PRODUCTS for t in terms}
        self.assertEqual(by_term["IZABAN"], "Empagliflozin")
        self.assertEqual(by_term["PROSMID"], "Apalutamide")
        self.assertEqual(by_term["VEOZAH"], "Fezolinetant")
        self.assertEqual(by_term["ZYNQUISTA"], "Sotagliflozin")
        self.assertEqual(by_term["ESPEROCT"], "Turoctocog alfa pegol")

    def test_ranitidine_trap_is_excluded(self):
        """A bare "RANI" returns ten RANITIDINA rows on the live portal."""
        every_term = [t for _, terms in config.GT_SEARCH_PRODUCTS for t in terms]
        self.assertNotIn("RANI", every_term)
        self.assertIn("RANIVISIO", every_term)

    def test_both_spellings_of_the_gliflozins_are_searched(self):
        by_inn = dict(config.GT_SEARCH_PRODUCTS)
        self.assertIn("DAPAGLIFOZINA", by_inn["Dapagliflozin"])    # como lo escribió el PO
        self.assertIn("DAPAGLIFLOZINA", by_inn["Dapagliflozin"])   # grafía correcta
        self.assertIn("EMPAGLIFOZINA", by_inn["Empagliflozin"])
        self.assertIn("EMPAGLIFLOZINA", by_inn["Empagliflozin"])

    def test_no_duplicate_search_terms(self):
        every_term = [t for _, terms in config.GT_SEARCH_PRODUCTS for t in terms]
        self.assertEqual(len(every_term), len(set(every_term)))

    def test_panel_molecules_resolve_to_the_canonical_inn(self):
        """So a GT brand row groups with the same molecule elsewhere."""
        self.assertEqual(normalize._canonical_molecule("EMPAGLIFLOZIN"), "EMPAGLIFLOZIN")
        self.assertEqual(normalize._canonical_molecule("APALUTAMIDE"), "APALUTAMIDE")

    def test_molecules_the_po_introduced_are_now_in_the_global_panel(self):
        """Aflibercept and Rivaroxaban arrived through this list and were promoted.

        While they lived only here, the molecule x country matrix showed them as if
        they had been searched everywhere and existed only in Guatemala.
        """
        panel = {m["inn"] for m in config.MOLECULES}
        self.assertIn("Aflibercept", panel)
        self.assertIn("Rivaroxaban", panel)

    def test_only_the_iud_group_remains_outside_the_panel(self):
        panel = {m["inn"] for m in config.MOLECULES}
        gt_only = {inn for inn, _ in config.GT_SEARCH_PRODUCTS if inn not in panel}
        self.assertEqual(gt_only, {"Levonorgestrel (DIU)"})

    def test_promoted_molecules_are_searched_by_inn_too(self):
        """The panel search uses the INN; the brands stay for the GT product search."""
        afl = next(m for m in config.MOLECULES if m["inn"] == "Aflibercept")
        self.assertIn("AFLIBERCEPT", config.search_terms(afl))
        riv = next(m for m in config.MOLECULES if m["inn"] == "Rivaroxaban")
        self.assertIn("RIVAROXABAN", config.search_terms(riv))
        self.assertIn("RIVAROXABÁN", config.search_terms(riv))  # forma acentuada


class TestNarrowingByMolecule(unittest.TestCase):
    def test_full_panel_searches_everything(self):
        self.assertEqual(config.gt_search_products(config.MOLECULES),
                         config.GT_SEARCH_PRODUCTS)

    def test_single_molecule_narrows_the_search(self):
        picked = config.gt_search_products(config.molecules_for("empagliflozin"))
        self.assertEqual([inn for inn, _ in picked], ["Empagliflozin"])

    def test_molecule_without_gt_products_returns_nothing(self):
        self.assertEqual(config.gt_search_products(config.molecules_for("macitentan")), [])

    def test_ad_hoc_molecule_dict_does_not_raise(self):
        """A fixture without an `inn` key must resolve, not blow up."""
        config.gt_search_products([{"latam_term": "REGORAFENIB"}])

    def test_no_molecules_searches_everything(self):
        self.assertEqual(config.gt_search_products([]), config.GT_SEARCH_PRODUCTS)



class TestSafetyNet(unittest.TestCase):
    """The brand list runs first; the panel's own INNs follow as a safety net.

    Measured on the live portal: the PO's list omits lenvatinib and macitentan, and
    both ARE registered in Guatemala (LENVATINIB Neoethicals 10 mg, MACITENTAN Para
    Farmacias 10 mg). A brand-only search dropped them without a trace.
    """

    def _plan(self, molecules=None):
        from extractors import gt
        return gt._search_plan(molecules if molecules is not None else config.MOLECULES)

    def test_brands_are_searched_before_the_panel_terms(self):
        plan = self._plan()
        listed = [inn for inn, _ in config.GT_SEARCH_PRODUCTS]
        self.assertEqual([inn for inn, _ in plan][:len(listed)], listed)

    def test_molecules_missing_from_the_list_are_recovered(self):
        covered = {inn for inn, _ in self._plan()}
        self.assertIn("Lenvatinib", covered)
        self.assertIn("Macitentan", covered)

    def test_a_molecule_already_in_the_list_is_not_searched_twice(self):
        plan = self._plan()
        labels = [inn for inn, _ in plan]
        self.assertEqual(labels.count("Empagliflozin"), 1)
        self.assertEqual(labels.count("Enzalutamide"), 1)

    def test_every_panel_molecule_ends_up_covered(self):
        covered = {inn.upper() for inn, _ in self._plan()}
        for m in config.MOLECULES:
            self.assertIn(m["inn"].upper(), covered, m["inn"])

    def test_ad_hoc_molecule_without_inn_does_not_raise(self):
        plan = self._plan([{"latam_term": "REGORAFENIB", "aliases": []}])
        self.assertTrue(plan)


class TestContraceptiveGroupResolved(unittest.TestCase):
    def test_iud_brands_map_to_levonorgestrel(self):
        """ASERTIA, ELOIRA, LILETTA, MIA CARE, MAHELY and ENGYNO are confirmed
        levonorgestrel intrauterine systems; EMILY and FIONA ride with them."""
        by_term = {t: inn for inn, terms in config.GT_SEARCH_PRODUCTS for t in terms}
        for brand in ("ASERTIA", "ELOIRA", "ENGYNO", "EMILY",
                      "MAHELY", "LILETTA", "FIONA", "MIA CARE"):
            self.assertEqual(by_term[brand], "Levonorgestrel (DIU)", brand)


if __name__ == "__main__":
    unittest.main(verbosity=2)
