"""Tests for src/ingestion.py"""

import os
import tempfile
import unittest

from src.ingestion import IngestionError, load_resume


class TestLoadResumeUnsupported(unittest.TestCase):
    def test_unsupported_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            with self.assertRaises(IngestionError):
                load_resume(path)
        finally:
            os.unlink(path)

    def test_nonexistent_file_raises(self):
        with self.assertRaises(Exception):
            load_resume("/nonexistent/path/resume.pdf")


class TestExtractTextFromDocx(unittest.TestCase):
    def test_docx_extraction(self):
        """Create a minimal DOCX in memory and verify text extraction."""
        from docx import Document
        from src.ingestion import extract_text_from_docx

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name

        doc = Document()
        doc.add_paragraph("Jane Doe")
        doc.add_paragraph("jane@example.com")
        doc.save(path)

        try:
            text = extract_text_from_docx(path)
            self.assertIn("Jane Doe", text)
            self.assertIn("jane@example.com", text)
        finally:
            os.unlink(path)

    def test_empty_docx_raises_ingestion_error(self):
        from docx import Document
        from src.ingestion import load_resume

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name

        doc = Document()
        doc.save(path)

        try:
            with self.assertRaises(IngestionError):
                load_resume(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
