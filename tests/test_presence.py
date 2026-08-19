"""
Presence rows (#2): novel molecules expected to have ~0 LATAM registrations get a
NULL-filled "we searched, found nothing" row per successfully-searched country,
instead of silently vanishing from the report.

Contract:
    * only molecules flagged track_if_absent produce presence rows
    * a (molecule, country) with a REAL record produces no presence row
    * presence rows are emitted only for countries actually searched
    * presence rows are valid canonical rows (PK present) tagged record_type NO_DATA
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import config  # noqa: E402
import presence  # noqa: E402
import normalize  # noqa: E402

FLAGGED = [m["latam_term"].upper() for m in config.MOLECULES if m.get("track_if_absent")]


def real_row(term, cc, rtype="APPROVAL"):
    return {"registration_number": "R1", "molecule_search_term": term,
            "country_code": cc, "record_type": rtype}


class TestPresenceRows(unittest.TestCase):
    def test_flagged_molecules_are_configured(self):
        # Sanity: the three novel molecules carry the flag.
        self.assertEqual(len(FLAGGED), 3)
        self.assertIn("VALOCTOCOGENE ROXAPARVOVEC", FLAGGED)

    def test_absent_flagged_molecule_gets_one_row_per_country(self):
        rows = presence.generate_presence_rows([], config.MOLECULES, {"CO", "PE"})
        self.assertEqual(len(rows), len(FLAGGED) * 2)
        self.assertTrue(all(r["record_type"] == "NO_DATA" for r in rows))

    def test_no_presence_when_real_record_exists(self):
        existing = [real_row("VALOCTOCOGENE ROXAPARVOVEC", "CO")]
        rows = presence.generate_presence_rows(existing, config.MOLECULES, {"CO", "PE"})
        pairs = {(r["molecule_search_term"], r["country_code"]) for r in rows}
        self.assertNotIn(("VALOCTOCOGENE ROXAPARVOVEC", "CO"), pairs)  # has data -> no row
        self.assertIn(("VALOCTOCOGENE ROXAPARVOVEC", "PE"), pairs)     # still absent in PE

    def test_no_data_record_type_does_not_count_as_data(self):
        # A prior NO_DATA row must not suppress a fresh presence row.
        prior = [presence._presence_row("MARSTACIMAB", "CO", "01/01/2026")]
        rows = presence.generate_presence_rows(prior, config.MOLECULES, {"CO"})
        pairs = {(r["molecule_search_term"], r["country_code"]) for r in rows}
        self.assertIn(("MARSTACIMAB", "CO"), pairs)

    def test_non_flagged_molecule_never_gets_presence(self):
        rows = presence.generate_presence_rows([], config.MOLECULES, {"CO", "PE", "SV"})
        terms = {r["molecule_search_term"] for r in rows}
        self.assertNotIn("REGORAFENIB", terms)
        self.assertNotIn("TADAFILO", terms)

    def test_only_searched_countries(self):
        self.assertEqual(presence.generate_presence_rows([], config.MOLECULES, set()), [])
        rows = presence.generate_presence_rows([], config.MOLECULES, {"SV"})
        self.assertEqual({r["country_code"] for r in rows}, {"SV"})

    def test_row_is_valid_canonical(self):
        row = presence.generate_presence_rows([], config.MOLECULES, {"CO"})[0]
        # All 19 canonical fields present; PK satisfied; HA resolved.
        for f in normalize.CANONICAL_FIELDS:
            self.assertIn(f, row)
        self.assertTrue(row["registration_number"])
        self.assertEqual(row["health_authority"], "INVIMA")
        # normalize_row must accept it (PK not dropped).
        self.assertIsNotNone(normalize.normalize_row(row))

    def test_toggle_disables_generation(self):
        with mock.patch.object(config, "EMIT_PRESENCE_ROWS", False):
            self.assertEqual(presence.generate_presence_rows([], config.MOLECULES, {"CO"}), [])

    def test_respects_molecule_filter(self):
        # When the run is narrowed to a non-flagged molecule, no presence rows.
        only_rego = config.molecules_for("regorafenib")
        self.assertEqual(presence.generate_presence_rows([], only_rego, {"CO"}), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
