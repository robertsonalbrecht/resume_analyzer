"""Output compilation and CSV export."""

import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

OUTPUT_COLUMNS = [
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
    "completeness_score",
    "date_added",
    "source_file",
]


def build_record(
    source_file: str,
    full_name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    linkedin_url: Optional[str],
    location: Optional[str],
    years_of_experience: float,
    pe_firms: List[str],
    industry_map: Dict[str, Optional[str]],
    work_history: list,
    seniority_level: str,
    profile_summary: Optional[str],
) -> Dict:
    """Build a flat record dict from extracted components."""
    # Deduplicate non-None industries from the industry map values
    industries = list(dict.fromkeys(
        tag for tag in industry_map.values() if tag is not None
    ))

    # functional_expertise: title from the most recent WorkEntry (highest index with title)
    functional_expertise = None
    for entry in reversed(work_history):
        if getattr(entry, "title", ""):
            functional_expertise = entry.title
            break

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
        "location": location,
        "years_of_experience": years_of_experience,
        "pe_firms": pe_firms,
        "industries": industries,
        "functional_expertise": functional_expertise,
        "company_size": None,  # requires external lookup
        "seniority_level": seniority_level,
        "profile_summary": profile_summary,
        "completeness_score": None,  # filled in by scorer
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "source_file": os.path.basename(source_file),
        "pe_detection_ran": True,
    }


def _format_field(value) -> str:
    """Format a field value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    return str(value)


def compile_results(records: List[Dict]) -> pd.DataFrame:
    """Convert a list of record dicts into a DataFrame with OUTPUT_COLUMNS."""
    rows = []
    for record in records:
        row = {col: _format_field(record.get(col)) for col in OUTPUT_COLUMNS}
        rows.append(row)
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def export_to_csv(records: List[Dict], output_path: str):
    """Write records to a CSV file with UTF-8 BOM encoding for Excel compatibility."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df = compile_results(records)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return df
