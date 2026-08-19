"""
Approval dates for the two registries that publish none.

Honduras (ARSA) — the Excel has no date column, but the registration number encodes
month and year: ``HN-M-MMYY-NNNN``. Verified across all 72 HN-prefixed rows of a live
extract: the first pair spans 01-12 (all twelve months) while the second only spans
18-25, so the second pair is the YEAR, not a day. There is no day component, so the
derived date is month-precision anchored to the 1st.

Guatemala (MSPAS) — publishes no approval date either, but a Guatemalan sanitary
registration runs for a fixed five-year term, so the issue date is the published
expiration date minus five years. Verified on a live extract: 29/29 rows carry an
expiration date and the derived issue years (2022-2026) are coherent. This yields
day precision, unlike Honduras.
"""

import os
import sys
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import report  # noqa: E402
from extractors.gt import _issue_from_expiry as gt_issue  # noqa: E402
from extractors.hn import approval_date_from_registration as derive  # noqa: E402


class TestHondurasDateFromRegistration(unittest.TestCase):
    def test_month_and_year_are_decoded(self):
        self.assertEqual(derive("HN-M-0723-0046"), "01/07/2023")   # julio 2023
        self.assertEqual(derive("HN-M-1218-0014"), "01/12/2018")   # diciembre 2018
        self.assertEqual(derive("HN-M-0119-0203"), "01/01/2019")   # enero 2019

    def test_second_pair_is_the_year_not_a_day(self):
        """The regression guard: 0425 is April 2025, never "day 25 of month 04"."""
        self.assertEqual(derive("HN-M-0425-0041"), "01/04/2025")

    def test_day_is_anchored_to_the_first(self):
        """Month precision only — anchoring at the 1st never overstates recency."""
        self.assertTrue(derive("HN-M-0521-0041").startswith("01/"))

    def test_legacy_numeric_registration_yields_nothing(self):
        """The old 5-digit format encodes no date — better empty than invented."""
        for legacy in ("45992", "46100", "46459"):
            self.assertIsNone(derive(legacy))

    def test_impossible_month_is_rejected(self):
        self.assertIsNone(derive("HN-M-1325-0001"))   # mes 13
        self.assertIsNone(derive("HN-M-0025-0001"))   # mes 00

    def test_garbage_input_is_safe(self):
        for bad in (None, "", "   ", "INVIMA 2025M-001", "HN-M-XXXX-0001"):
            self.assertIsNone(derive(bad))

    def test_output_parses_as_a_canonical_date(self):
        import normalize
        self.assertEqual(normalize.parse_date(derive("HN-M-0723-0046")), "01/07/2023")


class TestGuatemalaIssueFromExpiry(unittest.TestCase):
    def test_five_year_term_is_subtracted(self):
        self.assertEqual(gt_issue("28/09/2028"), "28/09/2023")
        self.assertEqual(gt_issue("06/02/2030"), "06/02/2025")
        self.assertEqual(gt_issue("17/04/2028"), "17/04/2023")

    def test_day_precision_is_preserved(self):
        """Unlike Honduras, the day survives — it comes from a real published date."""
        self.assertEqual(gt_issue("19/08/2030"), "19/08/2025")

    def test_leap_day_steps_back_to_the_28th(self):
        """29/02/2028 minus 5 years lands on a non-leap year."""
        self.assertEqual(gt_issue("29/02/2028"), "28/02/2023")

    def test_missing_expiration_yields_nothing(self):
        for empty in (None, "", "   "):
            self.assertIsNone(gt_issue(empty))

    def test_unparseable_expiration_yields_nothing(self):
        self.assertIsNone(gt_issue("sin fecha"))

    def test_output_parses_as_a_canonical_date(self):
        import normalize
        self.assertEqual(normalize.parse_date(gt_issue("28/09/2028")), "28/09/2023")

    def test_derived_date_is_not_flagged_as_placeholder(self):
        """A real derived date must reach the recent-approvals signal."""
        row = {f: None for f in report.CANONICAL_FIELDS}
        row.update({"approval_date": gt_issue("28/09/2028"),
                    "extraction_date": date.today().strftime("%d/%m/%Y")})
        self.assertFalse(report._has_placeholder_date(row))


class TestPlaceholderDatesExcludedFromRecentSignal(unittest.TestCase):
    """A placeholder date must not masquerade as a brand-new competitor approval."""

    def _row(self, approval, extraction, rtype="APPROVAL"):
        base = {f: None for f in report.CANONICAL_FIELDS}
        base.update({"registration_number": "R1", "country_code": "GT",
                     "record_type": rtype, "product_name": "P",
                     "approval_date": approval, "extraction_date": extraction})
        return base

    def test_stamped_row_is_not_a_recent_approval(self):
        today = date.today().strftime("%d/%m/%Y")
        rows = [self._row(today, today)]           # GT placeholder
        self.assertEqual(report.recent_approvals(rows), [])

    def test_genuinely_recent_approval_still_counts(self):
        today = date.today().strftime("%d/%m/%Y")
        rows = [self._row(today, "01/01/2020")]    # approved today, extracted earlier
        self.assertEqual(len(report.recent_approvals(rows)), 1)

    def test_derived_honduras_date_is_not_treated_as_placeholder(self):
        """HN dates come from the registration number, so they are real signal."""
        rows = [self._row(derive("HN-M-0723-0046"),
                          date.today().strftime("%d/%m/%Y"))]
        self.assertFalse(report._has_placeholder_date(rows[0]))

    def test_rows_without_dates_are_unaffected(self):
        self.assertFalse(report._has_placeholder_date(self._row(None, "18/08/2026")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
