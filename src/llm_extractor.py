"""LLM-based entity extractor — replaces regex/spaCy as the primary extractor.

Falls back to extract_entities() (spaCy/regex) on any failure.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.entity_extractor import ExtractedEntities, WorkEntry, extract_entities

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a resume parsing engine. "
    "Return only valid JSON — no markdown fences, no prose, no explanation."
)

MAX_TEXT_CHARS = 15_000


class LLMExtractor:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.last_fallback_reason: Optional[str] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def extract(self, raw_text: str) -> ExtractedEntities:
        """Extract entities via Claude; fall back to spaCy/regex on any error."""
        self.last_fallback_reason = None
        try:
            return self._extract_via_llm(raw_text)
        except Exception as exc:
            self.last_fallback_reason = str(exc)
            logger.warning("LLM extraction failed (%s); falling back to regex/spaCy.", exc)
            return extract_entities(raw_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_via_llm(self, text: str) -> ExtractedEntities:
        prompt = self._build_prompt(text[:MAX_TEXT_CHARS])
        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        return self._parse_response(raw)

    def _build_prompt(self, text: str) -> str:
        schema = """\
{
  "full_name": string or null,
  "email": string or null,
  "phone": string or null,
  "linkedin_url": string or null,
  "location": string or null,
  "work_history": [
    {
      "company": string,
      "title": string,
      "start_date": "YYYY-MM-DD" or null,
      "end_date": "YYYY-MM-DD" or null
    }
  ]
}"""
        rules = """\
Rules:
- work_history must be sorted descending — most recent role first.
- For a current/ongoing role: end_date = null.
- Year-only start date → use YYYY-01-01; year-only end date → use YYYY-12-31.
- Normalize phone to (NNN) NNN-NNNN format if it is a US number.
- Return JSON only — no markdown fences, no prose."""
        return (
            f"Parse the following resume and return a JSON object matching this schema:\n\n"
            f"{schema}\n\n"
            f"{rules}\n\n"
            f"Resume text:\n\"\"\"\n{text}\n\"\"\""
        )

    def _parse_response(self, raw: str) -> ExtractedEntities:
        # Strip accidental markdown fences if the model disobeys the prompt
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Drop first and last fence lines
            inner = lines[1:] if lines[0].startswith("```") else lines
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            cleaned = "\n".join(inner)

        data = json.loads(cleaned)

        def _str(val) -> Optional[str]:
            """Coerce empty string / None to None."""
            if val is None or val == "":
                return None
            return str(val)

        work_history = []
        for item in data.get("work_history") or []:
            start_str = _str(item.get("start_date"))
            end_str = _str(item.get("end_date"))
            work_history.append(WorkEntry(
                company=_str(item.get("company")) or "",
                title=_str(item.get("title")) or "",
                start_raw=start_str or "",
                end_raw=end_str or "Present",
                start_date=self._parse_date_str(start_str),
                end_date=self._parse_date_str(end_str),  # None → Present
            ))

        return ExtractedEntities(
            full_name=_str(data.get("full_name")),
            email=_str(data.get("email")),
            phone=_str(data.get("phone")),
            linkedin_url=_str(data.get("linkedin_url")),
            location=_str(data.get("location")),
            work_history=work_history,
        )

    def _parse_date_str(self, s: Optional[str]) -> Optional[datetime]:
        """Parse an ISO date string (YYYY-MM-DD, YYYY-MM, or YYYY) → datetime or None."""
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None
