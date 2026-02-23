"""Tests for src/completeness_scorer.py"""

import unittest

from src.completeness_scorer import score_completeness, TOTAL_FIELDS


class TestCompletenessScorer(unittest.TestCase):
    def _full_record(self):
        return {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "(415) 555-1234",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "location": "San Francisco, CA",
            "years_of_experience": 7.5,
            "pe_firms": [],           # empty but PE detection ran
            "pe_detection_ran": True,
            "industries": ["Technology/Software"],
            "functional_expertise": "Product Manager",
            "company_size": None,     # always None — counts as unpopulated
            "seniority_level": "Mid",
            "profile_summary": "A seasoned product manager...",
        }

    def test_full_record_minus_company_size(self):
        record = self._full_record()
        score = score_completeness(record)
        # 11/12 fields populated (company_size always None)
        self.assertAlmostEqual(score, 11 / 12 * 100, delta=0.5)

    def test_empty_record_scores_zero(self):
        record = {
            "full_name": None, "email": None, "phone": None,
            "linkedin_url": None, "location": None,
            "years_of_experience": 0.0, "pe_firms": [],
            "pe_detection_ran": False,
            "industries": [], "functional_expertise": None,
            "company_size": None, "seniority_level": None,
            "profile_summary": None,
        }
        score = score_completeness(record)
        self.assertEqual(score, 0.0)

    def test_pe_firms_empty_list_counts_if_detection_ran(self):
        record = {k: None for k in [
            "full_name", "email", "phone", "linkedin_url", "location",
            "years_of_experience", "industries", "functional_expertise",
            "company_size", "seniority_level", "profile_summary",
        ]}
        record["years_of_experience"] = 0.0
        record["pe_firms"] = []
        record["pe_detection_ran"] = True
        score = score_completeness(record)
        # Only pe_firms is populated
        self.assertAlmostEqual(score, 1 / TOTAL_FIELDS * 100, delta=0.1)

    def test_pe_firms_not_counted_when_detection_did_not_run(self):
        record = {k: None for k in [
            "full_name", "email", "phone", "linkedin_url", "location",
            "years_of_experience", "industries", "functional_expertise",
            "company_size", "seniority_level", "profile_summary",
        ]}
        record["years_of_experience"] = 0.0
        record["pe_firms"] = ["KKR"]  # non-empty but detection_ran=False
        record["pe_detection_ran"] = False
        score = score_completeness(record)
        self.assertEqual(score, 0.0)

    def test_zero_years_counts_as_unpopulated(self):
        record = self._full_record()
        record["years_of_experience"] = 0.0
        score = score_completeness(record)
        # Should be lower than the full score
        full_score = score_completeness(self._full_record())
        self.assertLess(score, full_score)

    def test_total_fields_is_12(self):
        self.assertEqual(TOTAL_FIELDS, 12)


if __name__ == "__main__":
    unittest.main()
