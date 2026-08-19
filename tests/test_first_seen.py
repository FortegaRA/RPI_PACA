"""
`extraction_date` must answer "when did this registration first appear".

The consolidated CSV feeds a SharePoint -> Power Automate -> Fabric flow whose
semantic model raises alerts on NEW competitor registrations. If every row were
re-stamped with the current date on every run, a registration first seen a year ago
would look identical to one that appeared this week, and the alert signal would be
worthless. Only genuinely new records carry the current run's date.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import rpi_cluster  # noqa: E402


def row(reg, cc="CR", rtype="APPROVAL", extraction="18/08/2026", status="APPROVED"):
    return {"registration_number": reg, "country_code": cc, "record_type": rtype,
            "extraction_date": extraction, "status": status}


class TestRestoreFirstSeen(unittest.TestCase):
    def test_known_record_keeps_its_original_date(self):
        previous = [row("R1", extraction="01/03/2026")]
        current = [row("R1", extraction="18/08/2026")]
        restored = rpi_cluster._restore_first_seen(current, previous)
        self.assertEqual(restored, 1)
        self.assertEqual(current[0]["extraction_date"], "01/03/2026")

    def test_new_record_keeps_todays_date(self):
        previous = [row("R1", extraction="01/03/2026")]
        current = [row("R1", extraction="18/08/2026"),
                   row("R2", extraction="18/08/2026")]   # nueva
        rpi_cluster._restore_first_seen(current, previous)
        by_reg = {r["registration_number"]: r for r in current}
        self.assertEqual(by_reg["R1"]["extraction_date"], "01/03/2026")
        self.assertEqual(by_reg["R2"]["extraction_date"], "18/08/2026",
                         "a genuinely new registration must carry the current date")

    def test_other_fields_still_refresh(self):
        """Only the date is carried over — corrections at the source must land."""
        previous = [row("R1", extraction="01/03/2026", status="APPROVED")]
        current = [row("R1", extraction="18/08/2026", status="EXPIRED")]
        rpi_cluster._restore_first_seen(current, previous)
        self.assertEqual(current[0]["status"], "EXPIRED")
        self.assertEqual(current[0]["extraction_date"], "01/03/2026")

    def test_same_number_in_another_country_is_a_different_record(self):
        previous = [row("R1", cc="HN", extraction="01/03/2026")]
        current = [row("R1", cc="CR", extraction="18/08/2026")]
        self.assertEqual(rpi_cluster._restore_first_seen(current, previous), 0)
        self.assertEqual(current[0]["extraction_date"], "18/08/2026")

    def test_approval_and_submission_are_tracked_separately(self):
        previous = [row("R1", rtype="SUBMISSION", extraction="01/03/2026")]
        current = [row("R1", rtype="APPROVAL", extraction="18/08/2026")]
        self.assertEqual(rpi_cluster._restore_first_seen(current, previous), 0)

    def test_no_previous_file_is_a_no_op(self):
        current = [row("R1", extraction="18/08/2026")]
        self.assertEqual(rpi_cluster._restore_first_seen(current, []), 0)
        self.assertEqual(current[0]["extraction_date"], "18/08/2026")

    def test_blank_previous_date_does_not_erase_the_current_one(self):
        previous = [row("R1", extraction="")]
        current = [row("R1", extraction="18/08/2026")]
        rpi_cluster._restore_first_seen(current, previous)
        self.assertEqual(current[0]["extraction_date"], "18/08/2026")

    def test_earliest_date_wins_when_duplicated_in_the_previous_file(self):
        previous = [row("R1", extraction="01/03/2026"), row("R1", extraction="05/06/2026")]
        current = [row("R1", extraction="18/08/2026")]
        rpi_cluster._restore_first_seen(current, previous)
        self.assertEqual(current[0]["extraction_date"], "01/03/2026")


if __name__ == "__main__":
    unittest.main(verbosity=2)
