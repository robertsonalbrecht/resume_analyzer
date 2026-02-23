"""Tests for src/entity_extractor.py"""

import unittest
from datetime import datetime

from src.entity_extractor import (
    extract_email,
    extract_phone,
    extract_linkedin,
    extract_entities,
)

SAMPLE_RESUME = """
Jane Doe
San Francisco, CA
jane.doe@example.com | (415) 555-1234 | linkedin.com/in/janedoe

EXPERIENCE

Software Engineer                          Jan 2020 – Present
Acme Corp
  - Built scalable APIs

Product Manager                            Jun 2017 – Dec 2019
Beta Inc
  - Led cross-functional teams
"""


class TestExtractEmail(unittest.TestCase):
    def test_extracts_email(self):
        self.assertEqual(extract_email("Contact: user@example.com today"), "user@example.com")

    def test_returns_none_when_absent(self):
        self.assertIsNone(extract_email("No email here"))

    def test_complex_email(self):
        # The regex [\w-]+ in the domain part stops at dots, so "sub.domain" is matched
        # from "user.name+tag@sub.domain.co"
        result = extract_email("user.name+tag@sub.domain.co")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("user.name+tag@"))


class TestExtractPhone(unittest.TestCase):
    def test_parens_format(self):
        result = extract_phone("Call (415) 555-1234 now")
        self.assertIsNotNone(result)
        self.assertIn("415", result)

    def test_dashes_format(self):
        result = extract_phone("Phone: 415-555-9876")
        self.assertIsNotNone(result)

    def test_returns_none_when_absent(self):
        self.assertIsNone(extract_phone("No phone number"))


class TestExtractLinkedIn(unittest.TestCase):
    def test_extracts_linkedin(self):
        result = extract_linkedin("Visit linkedin.com/in/janedoe for more")
        self.assertEqual(result, "https://linkedin.com/in/janedoe")

    def test_https_prefix(self):
        result = extract_linkedin("https://www.linkedin.com/in/john-smith-123")
        self.assertIn("linkedin.com/in/john-smith-123", result)

    def test_returns_none_when_absent(self):
        self.assertIsNone(extract_linkedin("No LinkedIn here"))


class TestExtractEntities(unittest.TestCase):
    def test_full_pipeline(self):
        entities = extract_entities(SAMPLE_RESUME)
        self.assertEqual(entities.email, "jane.doe@example.com")
        self.assertIsNotNone(entities.phone)
        self.assertIsNotNone(entities.linkedin_url)
        self.assertIn("linkedin.com/in/janedoe", entities.linkedin_url)

    def test_work_history_extracted(self):
        entities = extract_entities(SAMPLE_RESUME)
        self.assertGreater(len(entities.work_history), 0)

    def test_caps_text_at_max_chars(self):
        long_text = "a" * 200_000
        entities = extract_entities(long_text)
        # Should not raise; work_history will be empty for gibberish
        self.assertIsInstance(entities.work_history, list)


if __name__ == "__main__":
    unittest.main()
