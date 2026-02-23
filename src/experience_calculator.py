"""Work experience duration and seniority inference."""

import re
from datetime import datetime
from typing import Dict, List, Optional

from src.entity_extractor import WorkEntry


DAYS_PER_YEAR = 365.25

EXECUTIVE_TITLE_KEYWORDS = re.compile(
    r"\b(CEO|CFO|COO|CTO|CIO|CHRO|CMO|President|Managing Director|MD|"
    r"Partner|Principal|General Partner|GP|Head of|Chief)\b",
    re.IGNORECASE,
)

SENIOR_TITLE_KEYWORDS = re.compile(
    r"\b(Senior|Sr\.?|Director|VP|Vice President|Lead|Manager)\b",
    re.IGNORECASE,
)


def _merge_overlapping_ranges(ranges):
    """Merge a list of (start, end) datetime tuples, handling overlaps."""
    if not ranges:
        return []
    # Sort by start date
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]

    for current_start, current_end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            # Overlapping: extend end if needed
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


def calculate_total_experience(work_history: List[WorkEntry]) -> float:
    """Calculate total years of experience, merging overlapping date ranges."""
    now = datetime.now()
    ranges = []

    for entry in work_history:
        start = entry.start_date
        end = entry.end_date if entry.end_date else now

        if start is None:
            continue
        if start > now:
            continue
        if end > now:
            end = now

        if start >= end:
            continue

        ranges.append((start, end))

    merged = _merge_overlapping_ranges(ranges)
    total_days = sum((end - start).days for start, end in merged)
    return round(total_days / DAYS_PER_YEAR, 1)


def infer_seniority(total_years: float, work_history: List[WorkEntry]) -> str:
    """Infer seniority level from years of experience and title keywords."""
    # Check titles for overrides first
    for entry in work_history:
        if EXECUTIVE_TITLE_KEYWORDS.search(entry.title):
            return "Executive"

    for entry in work_history:
        if SENIOR_TITLE_KEYWORDS.search(entry.title):
            if total_years >= 8:
                return "Senior"

    # Threshold rules
    if total_years < 3:
        return "Junior"
    elif total_years < 8:
        return "Mid"
    elif total_years < 15:
        return "Senior"
    else:
        return "Executive"


def calculate_experience(work_history: List[WorkEntry]) -> Dict:
    """Main entry point: returns dict with years_of_experience and seniority_level."""
    total_years = calculate_total_experience(work_history)
    seniority = infer_seniority(total_years, work_history)
    return {
        "years_of_experience": total_years,
        "seniority_level": seniority,
    }
