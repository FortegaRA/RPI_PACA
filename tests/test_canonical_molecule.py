"""
Every row carries ONE molecule identity, whatever source it came from.

Each portal is searched in its own vocabulary — LATAM registries use the Spanish
spelling ("DAPAGLIFLOZINA"), EMA/FDA use the INN ("DAPAGLIFLOZIN"), and a couple of
molecules are tracked under a local shorthand ("RFVIII" for turoctocog alfa pegol).
Before this was centralized, the same molecule appeared under two different
`molecule_search_term` values, so the molecule x country matrix listed 34 rows for a
27-molecule panel and split each competitor's picture in half.

Canonicalization happens in normalize.py, so the extractors stay free to tag rows
however their source spells things.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import config  # noqa: E402
import normalize  # noqa: E402
import postfilter  # noqa: E402


class TestCanonicalInn(unittest.TestCase):
    def test_latam_and_inn_spellings_collapse(self):
        for spanish, inn in [("DAPAGLIFLOZINA", "DAPAGLIFLOZIN"),
                             ("EMPAGLIFLOZINA", "EMPAGLIFLOZIN"),
                             ("APALUTAMIDA", "APALUTAMIDE"),
                             ("ENZALUTAMIDA", "ENZALUTAMIDE"),
                             ("DAROLUTAMIDA", "DAROLUTAMIDE"),
                             ("FINERENONA", "FINERENONE")]:
            self.assertEqual(config.canonical_inn(spanish), inn)
            self.assertEqual(config.canonical_inn(inn), inn)

    def test_local_shorthand_resolves(self):
        # Peru/LATAM track turoctocog under a factor-VIII shorthand.
        self.assertEqual(config.canonical_inn("RFVIII"), "TUROCTOCOG ALFA PEGOL")

    def test_lookup_is_case_and_space_insensitive(self):
        self.assertEqual(config.canonical_inn("  dapagliflozin "), "DAPAGLIFLOZIN")

    def test_every_panel_term_resolves(self):
        """No molecule in the panel may be left with an unresolvable variant."""
        for m in config.MOLECULES:
            variants = [m["inn"], m["latam_term"], m["ema_term"], m["fda_term"]]
            variants += list(m.get("aliases", []))
            for v in variants:
                if v:
                    self.assertEqual(config.canonical_inn(v), m["inn"].upper(),
                                     f"{v!r} no resuelve a {m['inn']}")

    def test_unknown_term_returns_none(self):
        self.assertIsNone(config.canonical_inn("MOLECULA-QUE-NO-EXISTE"))


class TestNormalizeAppliesCanonicalTerm(unittest.TestCase):
    def _term(self, raw_term):
        row = normalize.normalize_row({"registration_number": "R1",
                                       "molecule_search_term": raw_term})
        return row["molecule_search_term"]

    def test_row_gets_canonical_identity(self):
        self.assertEqual(self._term("DAPAGLIFLOZINA"), "DAPAGLIFLOZIN")
        self.assertEqual(self._term("DAPAGLIFLOZIN"), "DAPAGLIFLOZIN")

    def test_latam_and_ema_rows_share_one_label(self):
        """The whole point: a LATAM row and an EMA row group together."""
        self.assertEqual(self._term("EMPAGLIFLOZINA"), self._term("EMPAGLIFLOZIN"))

    def test_adhoc_term_is_preserved(self):
        """An ad-hoc --molecule search must not be silently relabelled."""
        self.assertEqual(self._term("PARACETAMOL"), "PARACETAMOL")

    def test_keyword_default_is_canonicalized_too(self):
        row = normalize.normalize_row({"registration_number": "R1"},
                                      molecule_search_term="ENZALUTAMIDA")
        self.assertEqual(row["molecule_search_term"], "ENZALUTAMIDE")


class TestPostFiltersStillMatchCanonicalRows(unittest.TestCase):
    """Post-filters key off molecule_search_term — they must know the INN too."""

    def _row(self, term, name="", hint=""):
        return {"molecule_search_term": term, "product_name": name,
                "api": "", "applicant": "", "_indication_hint": hint}

    def test_bevacizumab_filter_applies_to_canonical_label(self):
        canonical = config.canonical_inn("BEVACIZUMAB")
        kept, dropped = postfilter.apply_post_filters(
            [self._row(canonical, name="AVASTIN", hint="cancer colorrectal")],
            config.MOLECULES)
        self.assertEqual(kept, [], "the systemic-oncology row must still be dropped")
        self.assertEqual(sum(dropped.values()), 1)

    def test_ranibizumab_biosimilar_survives_under_canonical_label(self):
        canonical = config.canonical_inn("RANIBIZUMAB")
        kept, _ = postfilter.apply_post_filters(
            [self._row(canonical, name="RANIVISIO")], config.MOLECULES)
        self.assertEqual(len(kept), 1)

    def test_unfiltered_molecule_passes(self):
        kept, dropped = postfilter.apply_post_filters(
            [self._row("REGORAFENIB", name="STIVARGA")], config.MOLECULES)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
