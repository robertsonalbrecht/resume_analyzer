"""Main CLI entry point for the resume parsing batch pipeline.

Usage:
    python -m src.main ./resumes/ --output ./output/results.csv --verbose
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from src.ingestion import load_resume, IngestionError
from src.entity_extractor import extract_entities
from src.industry_classifier import IndustryClassifier
from src.pe_detector import PEDetector
from src.experience_calculator import calculate_experience
from src.ai_synthesizer import AISynthesizer
from src.completeness_scorer import score_completeness
from src.output_module import build_record, export_to_csv

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

# Paths to data files relative to this file's parent directory
_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
DATA_DIR = _PROJECT_ROOT / "data"
COMPANY_LOOKUP_PATH = str(DATA_DIR / "company_industry_lookup.csv")
PE_FIRMS_PATH = str(DATA_DIR / "pe_firms.csv")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Batch resume parser — extracts structured candidate data to CSV."
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing PDF/DOCX resume files.",
    )
    parser.add_argument(
        "--output",
        default="./output/results.csv",
        help="Path for the output CSV file (default: ./output/results.csv).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def find_resumes(input_dir: str):
    """Return list of resume file paths in input_dir."""
    p = Path(input_dir)
    if not p.exists():
        print(f"Error: input directory {input_dir!r} does not exist.", file=sys.stderr)
        sys.exit(1)

    files = [
        str(f) for f in sorted(p.iterdir())
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return files


def process_file(file_path: str, classifier, detector, synthesizer) -> dict:
    """Process a single resume file through the full pipeline."""
    # 1. Ingest
    raw_text = load_resume(file_path)

    # 2. Extract entities
    entities = extract_entities(raw_text)

    # 3. Classify industries
    company_names = [
        e.company for e in entities.work_history if e.company
    ]
    industry_map = classifier.classify_all(company_names)

    # 4. Detect PE firms
    pe_firms = detector.detect(company_names)

    # 5. Calculate experience
    exp = calculate_experience(entities.work_history)

    # 6. AI synthesis
    industries = list(dict.fromkeys(
        tag for tag in industry_map.values() if tag is not None
    ))
    ai_result = synthesizer.synthesize(
        full_name=entities.full_name,
        location=entities.location,
        years_of_experience=exp["years_of_experience"],
        seniority_level=exp["seniority_level"],
        work_history=entities.work_history,
        industries=industries,
        pe_firms=pe_firms,
    )

    # 7. Build record
    record = build_record(
        source_file=file_path,
        full_name=entities.full_name,
        email=entities.email,
        phone=entities.phone,
        linkedin_url=entities.linkedin_url,
        location=entities.location,
        years_of_experience=exp["years_of_experience"],
        pe_firms=pe_firms,
        industry_map=industry_map,
        work_history=entities.work_history,
        seniority_level=ai_result.get("seniority_level", exp["seniority_level"]),
        profile_summary=ai_result.get("profile_summary"),
    )

    # 8. Score completeness
    record["completeness_score"] = score_completeness(record)

    return record


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.verbose)

    files = find_resumes(args.input_dir)
    if not files:
        print(f"No PDF or DOCX files found in {args.input_dir!r}.")
        sys.exit(0)

    print(f"Found {len(files)} resume(s) to process.")

    # Instantiate shared components once
    classifier = IndustryClassifier(COMPANY_LOOKUP_PATH)
    detector = PEDetector(PE_FIRMS_PATH)
    synthesizer = AISynthesizer()

    records = []
    errors = []

    for file_path in files:
        filename = os.path.basename(file_path)
        if args.verbose:
            print(f"  Processing: {filename}")
        try:
            record = process_file(file_path, classifier, detector, synthesizer)
            records.append(record)
        except IngestionError as e:
            msg = f"Ingestion failed: {e}"
            errors.append((filename, msg))
            logging.warning("Skipping %s — %s", filename, msg)
        except Exception as e:
            msg = str(e)
            errors.append((filename, msg))
            logging.warning("Skipping %s — unexpected error: %s", filename, msg)

    # Export results
    if records:
        export_to_csv(records, args.output)

    # Print summary
    print()
    print("=== BATCH COMPLETE ===")
    print(f"Processed:  {len(records)} records")
    print(f"Errors:     {len(errors)} files failed")
    for fname, err in errors:
        print(f"  - {fname}: {err}")

    if records:
        avg_score = sum(r.get("completeness_score", 0) for r in records) / len(records)
        print(f"Avg completeness score: {avg_score:.1f}%")
        print(f"Output written to: {args.output}")
    else:
        print("No records to write.")


if __name__ == "__main__":
    main()
