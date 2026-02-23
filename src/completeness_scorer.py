"""Completeness scoring for extracted resume records."""

from typing import Dict

# The 12 schema fields tracked for completeness
SCORED_FIELDS = [
    "full_name",
    "email",
    "phone",
    "linkedin_url",
    "location",
    "years_of_experience",
    "pe_firms",
    "industries",
    "functional_expertise",
    "company_size",
    "seniority_level",
    "profile_summary",
]

TOTAL_FIELDS = len(SCORED_FIELDS)  # 12


def score_completeness(record: Dict) -> float:
    """Return completeness as a percentage (0–100) rounded to 1 decimal place.

    Special rules:
    - pe_firms: scored as populated if record["pe_detection_ran"] is True
      (empty list is valid — means "no PE experience")
    - years_of_experience == 0.0 counts as unpopulated
    - company_size: None is always unpopulated (external lookup not in scope)
    """
    populated = 0

    for field in SCORED_FIELDS:
        value = record.get(field)

        if field == "pe_firms":
            if record.get("pe_detection_ran", False):
                populated += 1
        elif field == "years_of_experience":
            if value is not None and value != 0.0:
                populated += 1
        elif value is not None and value != "" and value != []:
            populated += 1

    return round(populated / TOTAL_FIELDS * 100, 1)
