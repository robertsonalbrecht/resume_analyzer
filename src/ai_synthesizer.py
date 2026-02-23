"""AI-powered profile summarization and seniority confirmation via Claude."""

import logging
import os
import re
from typing import Dict, List, Optional

from anthropic import Anthropic, APIError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a talent researcher at a PE firm. "
    "Summarize candidates factually based on provided data. "
    "Use the exact structured format specified."
)

VALID_SENIORITY = {"Junior", "Mid", "Senior", "Executive"}

RESPONSE_FORMAT = (
    "SUMMARY: <2-3 sentence narrative starting with title/level, not name>\n"
    "SENIORITY: <Junior|Mid|Senior|Executive>"
)


def _build_user_prompt(candidate: Dict) -> str:
    work_lines = []
    for entry in candidate.get("work_history", []):
        start = entry.get("start_raw", "")
        end = entry.get("end_raw", "Present")
        work_lines.append(
            f"  - {entry.get('title', 'N/A')} at {entry.get('company', 'N/A')} "
            f"({start} – {end})"
        )

    work_str = "\n".join(work_lines) if work_lines else "  No work history extracted."

    industries = ", ".join(candidate.get("industries", [])) or "Unknown"
    pe_firms = ", ".join(candidate.get("pe_firms", [])) or "None"

    return (
        f"Candidate Data:\n"
        f"  Name: {candidate.get('full_name', 'Unknown')}\n"
        f"  Location: {candidate.get('location', 'Unknown')}\n"
        f"  Total Experience: {candidate.get('years_of_experience', 0):.1f} years\n"
        f"  Seniority (calculated): {candidate.get('seniority_level', 'Unknown')}\n"
        f"  Industries: {industries}\n"
        f"  PE Firms: {pe_firms}\n"
        f"  Work History:\n{work_str}\n\n"
        f"Respond with exactly:\n{RESPONSE_FORMAT}"
    )


class AISynthesizer:
    def __init__(self):
        self._client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def synthesize(
        self,
        full_name: Optional[str],
        location: Optional[str],
        years_of_experience: float,
        seniority_level: str,
        work_history: list,
        industries: List[str],
        pe_firms: List[str],
    ) -> Dict:
        """Return {profile_summary, seniority_level} from Claude."""
        candidate = {
            "full_name": full_name,
            "location": location,
            "years_of_experience": years_of_experience,
            "seniority_level": seniority_level,
            "work_history": [
                {
                    "title": getattr(e, "title", ""),
                    "company": getattr(e, "company", ""),
                    "start_raw": getattr(e, "start_raw", ""),
                    "end_raw": getattr(e, "end_raw", "Present"),
                }
                for e in work_history
            ],
            "industries": industries,
            "pe_firms": pe_firms,
        }
        prompt = _build_user_prompt(candidate)

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            return self._parse_response(raw, fallback_seniority=seniority_level)
        except APIError as e:
            logger.warning("Claude API error during synthesis: %s", e)
            return {"profile_summary": None, "seniority_level": seniority_level}
        except Exception as e:
            logger.warning("Unexpected error during synthesis: %s", e)
            return {"profile_summary": None, "seniority_level": seniority_level}

    def _parse_response(self, raw: str, fallback_seniority: str) -> Dict:
        """Parse 'SUMMARY: ...\nSENIORITY: ...' response format."""
        summary = None
        seniority = fallback_seniority

        summary_match = re.search(r"SUMMARY:\s*(.+?)(?=\nSENIORITY:|$)", raw, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        seniority_match = re.search(r"SENIORITY:\s*(\w+)", raw)
        if seniority_match:
            candidate_seniority = seniority_match.group(1).strip()
            if candidate_seniority in VALID_SENIORITY:
                seniority = candidate_seniority
            else:
                logger.warning(
                    "Invalid seniority %r from Claude; using fallback %r",
                    candidate_seniority,
                    fallback_seniority,
                )

        return {"profile_summary": summary, "seniority_level": seniority}
