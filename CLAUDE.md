# Resume Analyzer — Claude Checkpoint

## Project Summary
Batch resume parsing pipeline: ingests PDF/DOCX resumes → extracts structured candidate data → outputs CSV.

## Status: Implementation Complete ✓
All modules written and 37/37 tests passing.

## File Structure
```
resume_analyzer/
├── .env                          # ANTHROPIC_API_KEY (do not commit)
├── requirements.txt
├── CLAUDE.md
├── src/
│   ├── __init__.py
│   ├── ingestion.py              # PDF + DOCX text extraction
│   ├── entity_extractor.py       # spaCy NER + regex (email, phone, LinkedIn, work history)
│   ├── industry_classifier.py    # CSV lookup → Claude API fallback + write-back cache
│   ├── pe_detector.py            # PE firm detection via normalized substring match
│   ├── experience_calculator.py  # Overlap-merge date ranges, seniority inference
│   ├── ai_synthesizer.py         # Claude claude-sonnet-4-6: profile summary + seniority
│   ├── completeness_scorer.py    # 12-field scoring
│   ├── output_module.py          # build_record(), export_to_csv() (utf-8-sig)
│   └── main.py                   # CLI entry point
├── data/
│   ├── company_industry_lookup.csv   # seed data + AI write-back cache
│   └── pe_firms.csv                  # 44 known PE firms
└── tests/
    ├── test_ingestion.py
    ├── test_entity_extractor.py
    ├── test_experience_calculator.py
    └── test_completeness_scorer.py
```

## Setup
```bash
# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Add API key
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

## Running the Pipeline
```bash
source venv/bin/activate
python -m src.main ./resumes_test --output ./output/results.csv --verbose
```

## Running Tests
```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Key Design Decisions
- spaCy model (`en_core_web_sm`) loaded once at module level in `entity_extractor.py`
- Industry classifier: exact match → partial match → Claude API; AI results written back to CSV cache
- PE detection: normalized substring match handles legal suffixes (KKR & Co. → KKR)
- Experience calculator merges overlapping date ranges before summing (handles consulting + FT overlap)
- Completeness scorer: `pe_firms` counted as populated if `pe_detection_ran=True` (empty list = "no PE" is valid)
- Output CSV: `utf-8-sig` encoding for Excel BOM compatibility; multi-values joined with `|`
- One file failure does not stop the batch; errors logged and summarized at end

## Output Schema (15 columns)
`full_name, email, phone, linkedin_url, location, years_of_experience, pe_firms, industries, functional_expertise, company_size, seniority_level, profile_summary, completeness_score, date_added, source_file`

## Next Steps / Possible Enhancements
- Add `company_size` lookup via external API (Crunchbase, LinkedIn)
- Enrich `functional_expertise` beyond most-recent title
- Add PDF resume test fixtures to `tests/`
- Hook up a CI workflow (GitHub Actions)
