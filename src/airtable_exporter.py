"""Airtable export module — pushes parsed resume records to the Contractors table."""

import os
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_API_TOKEN = os.getenv("AIRTABLE_API_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")

FIELD_MAP = {
    "full_name": "Full Name",
    "email": "Email",
    "phone": "Phone",
    "linkedin_url": "LinkedIn URL",
    "location": "Location",
    "years_of_experience": "Years of Operating Experience",
    "pe_firms": "Previous PE Firms Worked With",
    "industries": "Industries",
    "functional_expertise": "Functional Expertise",
    "company_size": "Company Size Experience",
}

MULTISELECT_FIELDS = {"industries", "functional_expertise"}

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _build_fields(record: Dict) -> Dict:
    fields = {}
    for our_key, airtable_key in FIELD_MAP.items():
        value = record.get(our_key)
        if value is None or value == "" or value == []:
            continue
        if our_key in MULTISELECT_FIELDS:
            value = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        elif isinstance(value, list):
            value = " | ".join(str(v) for v in value)
        fields[airtable_key] = value
    return fields


def _find_existing_by_email(email: str) -> Tuple[Optional[str], Optional[str]]:
    """Check Airtable for an existing record with this email.

    Returns (record_id_or_None, error_message_or_None).
    """
    if not email:
        return None, None
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_TOKEN}"}
    # Escape any double quotes in the email address
    safe_email = email.replace('"', '\\"')
    params = {
        "filterByFormula": f'LOWER({{Email}})=LOWER("{safe_email}")',
        "maxRecords": 1,
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.RequestException as e:
        return None, f"Duplicate check network error: {e}"

    if not resp.ok:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            detail = resp.text
        return None, f"Duplicate check failed (HTTP {resp.status_code}): {detail}"

    existing = resp.json().get("records", [])
    if existing:
        return existing[0]["id"], None
    return None, None


def _upload_attachment(record_id: str, file_bytes: bytes, filename: str) -> List[str]:
    """Upload a file to the Resume/CV field of an existing Airtable record."""
    suffix = os.path.splitext(filename)[1].lower()
    content_type = MIME_TYPES.get(suffix, "application/octet-stream")

    url = f"https://content.airtable.com/v0/{AIRTABLE_BASE_ID}/{record_id}/uploadAttachment"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_TOKEN}"}

    try:
        resp = requests.post(
            url,
            headers=headers,
            files={
                "file": (filename, file_bytes, content_type),
                "filename": (None, filename),
                "contentType": (None, content_type),
                "field": (None, "Resume/CV"),
            },
            timeout=60,
        )
    except requests.RequestException as e:
        return [f"File upload failed for '{filename}': {e}"]

    try:
        body = resp.json()
    except Exception:
        body = resp.text[:300]

    if resp.ok:
        return [f"DEBUG upload response ({resp.status_code}): {body}"]

    detail = body.get("error", {}).get("message", body) if isinstance(body, dict) else body
    return [f"File upload failed for '{filename}': HTTP {resp.status_code} — {detail}"]


def push_records(records: List[Dict]) -> Tuple[int, int, List[str]]:
    """Push records to Airtable, skip duplicates by email, then upload files.

    Returns (created_count, skipped_count, error_messages).
    Raises ValueError if credentials are missing from .env.
    """
    if not AIRTABLE_API_TOKEN or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_ID:
        raise ValueError(
            "Airtable credentials missing. Set AIRTABLE_API_TOKEN, "
            "AIRTABLE_BASE_ID, and AIRTABLE_TABLE_ID in .env"
        )

    create_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    to_create = []
    skipped_count = 0
    errors: List[str] = []

    for record in records:
        email = record.get("email") or ""
        if email:
            existing_id, check_err = _find_existing_by_email(email)
            if check_err:
                errors.append(check_err)
                # Abort rather than risk creating a duplicate
                continue
            if existing_id:
                skipped_count += 1
                continue
        to_create.append(record)

    created_count = 0

    for i in range(0, len(to_create), 10):
        batch = to_create[i : i + 10]
        payload = {
            "records": [{"fields": _build_fields(r)} for r in batch],
            "typecast": True,
        }
        try:
            resp = requests.post(create_url, headers=headers, json=payload, timeout=30)
        except requests.RequestException as e:
            errors.append(f"Batch {i // 10 + 1}: network error — {e}")
            continue

        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            errors.append(f"Batch {i // 10 + 1}: HTTP {resp.status_code} — {detail}")
            continue

        created_records = resp.json().get("records", [])
        created_count += len(created_records)

        for record, created in zip(batch, created_records):
            file_bytes = record.get("_file_bytes")
            file_name = record.get("_file_name")
            if file_bytes and file_name:
                errors.extend(_upload_attachment(created["id"], file_bytes, file_name))
            else:
                errors.append(f"No file data found for '{record.get('full_name', 'unknown')}' — attachment skipped.")

    return created_count, skipped_count, errors
