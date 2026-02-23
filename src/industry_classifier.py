"""Industry classification via lookup table and Claude API fallback."""

import logging
import os
from typing import Dict, List, Optional

import pandas as pd
from anthropic import Anthropic, APIError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

INDUSTRY_TAGS = [
    "Technology/Software",
    "Financial Services",
    "Healthcare/Life Sciences",
    "Business Services",
    "Industrials/Manufacturing",
    "Energy",
    "Retail/Consumer",
    "Real Estate",
    "Media/Entertainment",
    "Education",
    "Government/Non-Profit",
    "Other",
]

SYSTEM_PROMPT = (
    "Classify into exactly one industry from the list. Respond with only the tag."
)

USER_PROMPT_TEMPLATE = (
    "Classify {company_name} into one of: "
    + ", ".join(INDUSTRY_TAGS)
    + ". Respond with only the industry tag."
)


class IndustryClassifier:
    def __init__(self, lookup_path: str):
        self._lookup_path = lookup_path
        self._lookup: Dict[str, str] = {}
        self._new_entries: List[Dict] = []
        self._client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        df = pd.read_csv(lookup_path)
        for _, row in df.iterrows():
            name = str(row["company_name"]).strip().lower()
            self._lookup[name] = str(row["industry_tag"]).strip()

    def classify(self, company_name: str) -> Optional[str]:
        """Classify a single company: exact match → partial match → Claude API."""
        if not company_name or not company_name.strip():
            return None

        norm = company_name.strip().lower()

        # Exact match
        if norm in self._lookup:
            return self._lookup[norm]

        # Partial match: check if any known company name is a substring
        for known, tag in self._lookup.items():
            if known in norm or norm in known:
                return tag

        # Claude API fallback
        return self._classify_with_claude(company_name)

    def classify_all(self, names: List[str]) -> Dict[str, Optional[str]]:
        """Deduplicate, classify each name, return {name: tag} mapping."""
        unique_names = list(dict.fromkeys(n for n in names if n and n.strip()))
        result = {}
        for name in unique_names:
            result[name] = self.classify(name)
        self._save_new_entries()
        return result

    def _classify_with_claude(self, company_name: str) -> Optional[str]:
        """Call Claude API to classify a company; writes result back to CSV."""
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=20,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(company_name=company_name),
                    }
                ],
            )
            tag = response.content[0].text.strip()
            # Validate that the returned tag is in our list
            if tag not in INDUSTRY_TAGS:
                # Try case-insensitive match
                for known_tag in INDUSTRY_TAGS:
                    if known_tag.lower() == tag.lower():
                        tag = known_tag
                        break
                else:
                    tag = "Other"

            # Cache result
            norm = company_name.strip().lower()
            self._lookup[norm] = tag
            self._new_entries.append({
                "company_name": company_name,
                "industry_tag": tag,
                "source": "ai",
            })
            return tag
        except APIError as e:
            logger.warning("Claude API error classifying %r: %s", company_name, e)
            return None
        except Exception as e:
            logger.warning("Unexpected error classifying %r: %s", company_name, e)
            return None

    def _save_new_entries(self):
        """Append new AI-classified entries to the lookup CSV, deduplicating."""
        if not self._new_entries:
            return
        try:
            existing = pd.read_csv(self._lookup_path)
            new_df = pd.DataFrame(self._new_entries)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined.drop_duplicates(subset=["company_name"], keep="last", inplace=True)
            combined.to_csv(self._lookup_path, index=False)
            self._new_entries.clear()
        except Exception as e:
            logger.warning("Failed to save new industry entries: %s", e)
