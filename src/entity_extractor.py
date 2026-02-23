"""Named entity and contact field extraction from resume text."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import spacy
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

# Load once at module level
NLP = spacy.load("en_core_web_sm")

# --- Compiled regex constants ---

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")

# US phone: optional country code, 10 digits, various separators
PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?"
    r"(?:\(?\d{3}\)?[-.\s]?)"
    r"\d{3}[-.\s]?\d{4}"
)

LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.IGNORECASE)

# Matches common date range patterns: "Jan 2020 – Mar 2022", "2018 - Present", etc.
DATE_RANGE_PATTERN = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)?"
    r"\.?\s*\d{4}"
    r"\s*[-–—]\s*"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)?"
    r"\.?\s*(?:\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
    re.IGNORECASE,
)

MAX_TEXT_CHARS = 100_000


@dataclass
class WorkEntry:
    company: str
    title: str
    start_raw: str
    end_raw: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]  # None = Present


@dataclass
class ExtractedEntities:
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    location: Optional[str]
    work_history: List[WorkEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Contact field extractors
# ---------------------------------------------------------------------------

def extract_email(text: str) -> Optional[str]:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def extract_phone(text: str) -> Optional[str]:
    match = PHONE_RE.search(text)
    if not match:
        return None
    # Normalize: strip non-digit chars, keep US 10-digit
    digits = re.sub(r"\D", "", match.group(0))
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return match.group(0)


def extract_linkedin(text: str) -> Optional[str]:
    match = LINKEDIN_RE.search(text)
    if not match:
        return None
    return "https://" + match.group(0).lower()


def extract_name(doc: spacy.tokens.Doc) -> Optional[str]:
    """First PERSON entity in the first 20 tokens; fallback to first non-empty line."""
    first_tokens = doc[:20]
    for ent in first_tokens.as_doc().ents:
        if ent.label_ == "PERSON":
            return ent.text.strip()

    # Fallback: first non-empty line of the document text
    for line in doc.text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped.split()) <= 6:
            return stripped
    return None


def extract_location(doc: spacy.tokens.Doc) -> Optional[str]:
    """First GPE entity in the first 30 lines of the document."""
    lines = doc.text.splitlines()[:30]
    snippet = "\n".join(lines)
    snippet_doc = NLP(snippet)
    for ent in snippet_doc.ents:
        if ent.label_ == "GPE":
            return ent.text.strip()
    return None


# ---------------------------------------------------------------------------
# Work history extraction
# ---------------------------------------------------------------------------

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse a raw date string; return None if unparseable or future beyond 1 year."""
    if not raw:
        return None
    now = datetime.now()
    if re.search(r"present|current|now", raw, re.IGNORECASE):
        return now
    try:
        parsed = dateutil_parser.parse(raw, fuzzy=True, default=datetime(now.year, 1, 1))
        # Discard clearly wrong future dates (typos like 2204)
        if parsed > now + relativedelta(years=1):
            return None
        return parsed
    except (ValueError, OverflowError):
        return None


def _parse_date_range(range_str: str):
    """Split a date range string into (start_raw, end_raw) pair."""
    parts = re.split(r"\s*[-–—]\s*", range_str, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return range_str.strip(), ""


def extract_work_history(text: str) -> List[WorkEntry]:
    """Extract work history by anchoring on date range lines."""
    lines = text.splitlines()
    entries: List[WorkEntry] = []

    for i, line in enumerate(lines):
        match = DATE_RANGE_PATTERN.search(line)
        if not match:
            continue

        range_str = match.group(0)
        start_raw, end_raw = _parse_date_range(range_str)
        start_date = _parse_date(start_raw)
        end_date = _parse_date(end_raw)

        # Filter future start dates
        now = datetime.now()
        if start_date and start_date > now:
            continue

        # Search ±3 lines for company and title
        window_start = max(0, i - 3)
        window_end = min(len(lines), i + 4)
        context_lines = [
            l.strip()
            for l in lines[window_start:window_end]
            if l.strip() and not DATE_RANGE_PATTERN.search(l)
        ]

        company = context_lines[0] if len(context_lines) > 0 else ""
        title = context_lines[1] if len(context_lines) > 1 else ""

        if not company and not title:
            continue

        entries.append(WorkEntry(
            company=company,
            title=title,
            start_raw=start_raw,
            end_raw=end_raw,
            start_date=start_date,
            end_date=end_date,
        ))

    return entries


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> ExtractedEntities:
    """Extract all entities from resume text (capped at MAX_TEXT_CHARS)."""
    text = text[:MAX_TEXT_CHARS]
    doc = NLP(text)

    return ExtractedEntities(
        full_name=extract_name(doc),
        email=extract_email(text),
        phone=extract_phone(text),
        linkedin_url=extract_linkedin(text),
        location=extract_location(doc),
        work_history=extract_work_history(text),
    )
