"""Tests for src/experience_calculator.py"""

import unittest
from datetime import datetime

from src.entity_extractor import WorkEntry
from src.experience_calculator import (
    calculate_total_experience,
    infer_seniority,
    _merge_overlapping_ranges,
)


def make_entry(company, title, start, end=None):
    return WorkEntry(
        company=company,
        title=title,
        start_raw=str(start),
        end_raw=str(end) if end else "Present",
        start_date=start,
        end_date=end,
    )


class TestMergeOverlappingRanges(unittest.TestCase):
    def test_no_overlap(self):
        ranges = [
            (datetime(2015, 1, 1), datetime(2017, 1, 1)),
            (datetime(2018, 1, 1), datetime(2020, 1, 1)),
        ]
        merged = _merge_overlapping_ranges(ranges)
        self.assertEqual(len(merged), 2)

    def test_full_overlap(self):
        ranges = [
            (datetime(2015, 1, 1), datetime(2020, 1, 1)),
            (datetime(2016, 1, 1), datetime(2019, 1, 1)),
        ]
        merged = _merge_overlapping_ranges(ranges)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0], (datetime(2015, 1, 1), datetime(2020, 1, 1)))

    def test_partial_overlap(self):
        ranges = [
            (datetime(2015, 1, 1), datetime(2018, 6, 1)),
            (datetime(2018, 1, 1), datetime(2020, 1, 1)),
        ]
        merged = _merge_overlapping_ranges(ranges)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][0], datetime(2015, 1, 1))
        self.assertEqual(merged[0][1], datetime(2020, 1, 1))

    def test_empty_input(self):
        self.assertEqual(_merge_overlapping_ranges([]), [])


class TestCalculateTotalExperience(unittest.TestCase):
    def test_simple_non_overlapping(self):
        entries = [
            make_entry("A", "Dev", datetime(2015, 1, 1), datetime(2017, 1, 1)),
            make_entry("B", "Lead", datetime(2018, 1, 1), datetime(2020, 1, 1)),
        ]
        years = calculate_total_experience(entries)
        self.assertAlmostEqual(years, 4.0, delta=0.1)

    def test_overlapping_roles(self):
        entries = [
            make_entry("Consulting", "Consultant", datetime(2016, 1, 1), datetime(2019, 1, 1)),
            make_entry("FT Job", "Manager", datetime(2017, 6, 1), datetime(2020, 1, 1)),
        ]
        years = calculate_total_experience(entries)
        # Should not double-count 2017-06 to 2019-01
        # Merged: 2016-01 to 2020-01 ≈ 4 years
        self.assertLess(years, 5.0)
        self.assertGreater(years, 3.5)

    def test_present_end_date(self):
        entries = [
            make_entry("Corp", "Engineer", datetime(2020, 1, 1), None),
        ]
        years = calculate_total_experience(entries)
        self.assertGreater(years, 0)

    def test_no_entries(self):
        self.assertEqual(calculate_total_experience([]), 0.0)

    def test_entries_with_no_start_date(self):
        entry = WorkEntry(
            company="X", title="Y",
            start_raw="", end_raw="",
            start_date=None, end_date=None
        )
        self.assertEqual(calculate_total_experience([entry]), 0.0)


class TestInferSeniority(unittest.TestCase):
    def test_junior(self):
        self.assertEqual(infer_seniority(1.5, []), "Junior")

    def test_mid(self):
        self.assertEqual(infer_seniority(5.0, []), "Mid")

    def test_senior_by_years(self):
        self.assertEqual(infer_seniority(10.0, []), "Senior")

    def test_executive_by_years(self):
        self.assertEqual(infer_seniority(16.0, []), "Executive")

    def test_executive_by_title(self):
        entries = [make_entry("X", "CEO", datetime(2010, 1, 1), datetime(2015, 1, 1))]
        self.assertEqual(infer_seniority(2.0, entries), "Executive")

    def test_senior_by_title_with_sufficient_years(self):
        entries = [make_entry("X", "Senior Manager", datetime(2010, 1, 1), datetime(2020, 1, 1))]
        self.assertEqual(infer_seniority(10.0, entries), "Senior")


if __name__ == "__main__":
    unittest.main()
