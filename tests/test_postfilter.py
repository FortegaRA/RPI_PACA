"""
Post-filter unit tests (molecules.md strategy notes):

    Bevacizumab -> keep ophthalmic,        drop systemic oncology
    Ranibizumab -> keep biosimilars,       drop the originator (Lucentis)

The Tadalafil case (PAH_OR_OPHTHALMIC) was dropped from the live panel, but the
spec is retained as a template; its tests use an explicit fixture molecule
(``TADA_MOL``) so they still exercise the PAH/ophthalmic engine path.

Also verifies that the non-canonical `_indication_hint` used for these decisions
never leaks into the output CSV.
"""

import csv
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import config  # noqa: E402
import postfilter  # noqa: E402
import normalize  # noqa: E402

MOLS = config.MOLECULES

# Tadalafil was removed from the live panel; the PAH_OR_OPHTHALMIC spec is kept as
# a template, so its tests supply the molecule explicitly to exercise that path.
TADA_MOL = {"inn": "Tadalafil", "latam_term": "TADAFILO", "ema_term": "tadalafil",
            "fda_term": "tadalafil", "aliases": ["TADALAFIL", "TADALAFILO"],
            "post_filter": "PAH_OR_OPHTHALMIC"}
MOLS_WITH_TADA = list(config.MOLECULES) + [TADA_MOL]


def row(term, name="", api="", applicant="", hint=""):
    return {"molecule_search_term": term, "product_name": name, "api": api,
            "applicant": applicant, "_indication_hint": hint}


def kept_names(rows, molecules=MOLS):
    kept, _ = postfilter.apply_post_filters(rows, molecules)
    return [r["product_name"] for r in kept]


class TestTadalafil(unittest.TestCase):
    def test_keep_pah_brand(self):
        self.assertIn("ADCIRCA 20 MG",
                      kept_names([row("TADAFILO", name="ADCIRCA 20 MG")], MOLS_WITH_TADA))

    def test_keep_pah_indication_hint(self):
        r = row("TADAFILO", name="TADALAFILO 20 MG", hint="Hipertension arterial pulmonar")
        self.assertEqual(len(kept_names([r], MOLS_WITH_TADA)), 1)

    def test_keep_ophthalmic_hint(self):
        r = row("TADAFILO", name="TADALAFILO", hint="uso oftálmico")  # accented
        self.assertEqual(len(kept_names([r], MOLS_WITH_TADA)), 1)

    def test_drop_erectile_dysfunction(self):
        self.assertEqual(kept_names([row("TADALAFIL", name="CIALIS 5 MG")], MOLS_WITH_TADA), [])

    def test_drop_when_no_indication_signal(self):
        # Generic tadalafil with no PAH/ophthalmic evidence is excluded.
        self.assertEqual(kept_names([row("TADAFILO", name="TADALAFILO 5 MG")], MOLS_WITH_TADA), [])

    def test_not_tracked_means_no_filter_in_live_panel(self):
        # With Tadalafil out of config.MOLECULES, an ED row now passes untouched.
        self.assertEqual(kept_names([row("TADALAFIL", name="CIALIS 5 MG")]), ["CIALIS 5 MG"])


class TestBevacizumab(unittest.TestCase):
    def test_keep_ophthalmic(self):
        r = row("BEVACIZUMAB", name="AVASTIN", hint="inyección intravítrea oftálmica")
        self.assertEqual(len(kept_names([r])), 1)

    def test_drop_systemic_oncology(self):
        r = row("BEVACIZUMAB", name="AVASTIN 100 MG", hint="Cancer colorrectal metastasico")
        self.assertEqual(kept_names([r]), [])


class TestRanibizumab(unittest.TestCase):
    def test_drop_originator_by_applicant(self):
        self.assertEqual(kept_names([row("RANIBIZUMAB", name="LUCENTIS", applicant="Novartis")]), [])

    def test_drop_originator_by_brand(self):
        self.assertEqual(kept_names([row("RANIBIZUMAB", name="LUCENTIS 10 MG/ML",
                                         applicant="Generic Co")]), [])

    def test_keep_biosimilar_brand(self):
        self.assertIn("RANIVISIO", kept_names([row("RANIBIZUMAB", name="RANIVISIO",
                                                   applicant="Teva")]))

    def test_keep_nonoriginator_biologic(self):
        # A non-originator ranibizumab is a biosimilar by definition.
        r = row("RANIBIZUMAB", name="RANIBIZUMAB 10 MG/ML", applicant="Bioeq AG")
        self.assertEqual(len(kept_names([r])), 1)

    def test_keep_biosimilar_keyword(self):
        r = row("RANIBIZUMAB", name="RANIBIZUMAB BIOSIMILAR", applicant="Novartis")
        self.assertEqual(len(kept_names([r])), 1)  # keyword overrides originator applicant


class TestPassthroughAndCounts(unittest.TestCase):
    def test_non_filtered_molecule_passes(self):
        rows = [row("REGORAFENIB", name="STIVARGA"), row("EMPAGLIFLOZINA", name="JARDIANCE")]
        kept, dropped = postfilter.apply_post_filters(rows, MOLS)
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, {})

    def test_dropped_counts_are_reported(self):
        rows = [
            row("TADALAFIL", name="CIALIS"),          # drop
            row("TADALAFIL", name="CIALIS 20"),       # drop
            row("RANIBIZUMAB", name="LUCENTIS", applicant="Genentech"),  # drop
            row("TADAFILO", name="ADCIRCA"),          # keep
        ]
        kept, dropped = postfilter.apply_post_filters(rows, MOLS_WITH_TADA)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped.get("TADALAFIL"), 2)
        self.assertEqual(dropped.get("RANIBIZUMAB"), 1)

    def test_empty_input(self):
        self.assertEqual(postfilter.apply_post_filters([], MOLS), ([], {}))


class TestIndicationHintDoesNotLeak(unittest.TestCase):
    def test_hint_carried_by_normalize_but_not_written_to_csv(self):
        import rpi_cluster
        raw = {"registration_number": "R1", "country_code": "HN", "record_type": "APPROVAL",
               "molecule_search_term": "TADAFILO", "product_name": "ADCIRCA",
               "_indication_hint": "Hipertension pulmonar"}
        canon = normalize.normalize_row(raw)
        # The hint is available for the post-filter...
        self.assertEqual(canon.get("_indication_hint"), "Hipertension pulmonar")
        # ...but must never appear as a CSV column.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            rpi_cluster.write_canonical_csv([canon], path)
            with open(path, encoding="utf-8-sig", newline="") as fh:
                header = next(csv.reader(fh))
        self.assertNotIn("_indication_hint", header)
        self.assertEqual(header, normalize.CANONICAL_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
