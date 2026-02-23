"""PE firm detection from company name lists."""

import re
from typing import List, Set

import pandas as pd


def _normalize(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation for matching."""
    name = name.lower()
    name = re.sub(r"\b(llc|llp|inc\.?|corp\.?|ltd\.?|co\.?|lp|&amp;)\b", "", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


class PEDetector:
    def __init__(self, pe_csv_path: str):
        df = pd.read_csv(pe_csv_path)
        self._firms: List[str] = df["firm_name"].dropna().tolist()
        # Build normalized -> canonical mapping
        self._normalized: dict = {_normalize(f): f for f in self._firms}

    def detect(self, company_names: List[str]) -> List[str]:
        """Return canonical PE firm names found in the input company list."""
        found: List[str] = []
        for company in company_names:
            if not company:
                continue
            norm_company = _normalize(company)
            # Exact match
            if norm_company in self._normalized:
                found.append(self._normalized[norm_company])
                continue
            # Substring match: check if any PE firm name appears within the company name
            for norm_firm, canonical in self._normalized.items():
                if norm_firm and norm_firm in norm_company:
                    found.append(canonical)
                    break
        return list(dict.fromkeys(found))  # deduplicate, preserve order
