"""Streamlit web app for the Resume Analyzer pipeline."""

import os
import tempfile
from pathlib import Path

import streamlit as st

from src.ingestion import load_resume, IngestionError
from src.llm_extractor import LLMExtractor
from src.industry_classifier import IndustryClassifier
from src.pe_detector import PEDetector
from src.experience_calculator import calculate_experience
from src.ai_synthesizer import AISynthesizer
from src.completeness_scorer import score_completeness
from src.output_module import build_record, compile_results
from src.airtable_exporter import push_records

_ROOT = Path(__file__).parent
COMPANY_LOOKUP_PATH = str(_ROOT / "data" / "company_industry_lookup.csv")
PE_FIRMS_PATH = str(_ROOT / "data" / "pe_firms.csv")


@st.cache_resource
def load_components():
    return (
        IndustryClassifier(COMPANY_LOOKUP_PATH),
        PEDetector(PE_FIRMS_PATH),
        AISynthesizer(),
        LLMExtractor(),
    )


def _process_file(file_path: str, classifier, detector, synthesizer, extractor) -> dict:
    """Run the full pipeline; record includes _work_history for UI display."""
    raw_text = load_resume(file_path)
    entities = extractor.extract(raw_text)
    if extractor.last_fallback_reason:
        st.warning(
            f"LLM extractor fell back to regex/spaCy — results may be lower quality. "
            f"Reason: {extractor.last_fallback_reason}"
        )

    company_names = [e.company for e in entities.work_history if e.company]
    industry_map = classifier.classify_all(company_names)
    pe_firms = detector.detect(company_names)
    exp = calculate_experience(entities.work_history)

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
    record["completeness_score"] = score_completeness(record)
    record["_work_history"] = entities.work_history  # stored for expander display

    return record


def _init_session_state():
    if "records" not in st.session_state:
        st.session_state.records = []
    if "errors" not in st.session_state:
        st.session_state.errors = []
    if "processing" not in st.session_state:
        st.session_state.processing = False


def _render_sidebar(records, errors):
    with st.sidebar:
        st.title("Stats")
        st.metric("Records Processed", len(records))
        if records:
            avg = sum(r.get("completeness_score", 0) for r in records) / len(records)
            st.metric("Avg Completeness", f"{avg:.1f}%")
        else:
            st.metric("Avg Completeness", "—")
        st.metric("Errors", len(errors))


def _render_work_history(work_history):
    if not work_history:
        st.write("_No work history extracted._")
        return
    for entry in work_history:
        title = entry.title or "Unknown Title"
        company = entry.company or "Unknown Company"
        start = entry.start_raw or "?"
        end = entry.end_raw or "Present"
        st.write(f"- **{title}** @ {company} ({start} – {end})")


def main():
    st.set_page_config(page_title="Resume Analyzer", layout="wide")
    st.title("Resume Analyzer")

    _init_session_state()

    classifier, detector, synthesizer, extractor = load_components()

    # --- Upload section ---
    uploaded_files = st.file_uploader(
        "Upload resumes (PDF or DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
    )

    analyze_clicked = st.button(
        "▶ Analyze Resumes",
        disabled=not uploaded_files or st.session_state.processing,
    )

    if analyze_clicked and uploaded_files:
        st.session_state.records = []
        st.session_state.errors = []
        st.session_state.processing = True

        total = len(uploaded_files)
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing ({i + 1}/{total}): {uploaded_file.name}")
            suffix = Path(uploaded_file.name).suffix
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                try:
                    record = _process_file(tmp_path, classifier, detector, synthesizer, extractor)
                    record["source_file"] = uploaded_file.name
                    record["_file_bytes"] = Path(tmp_path).read_bytes()
                    record["_file_name"] = uploaded_file.name
                    st.session_state.records.append(record)
                except IngestionError as e:
                    st.session_state.errors.append(
                        (uploaded_file.name, f"Ingestion failed: {e}")
                    )
                except Exception as e:
                    st.session_state.errors.append((uploaded_file.name, str(e)))
                finally:
                    os.unlink(tmp_path)
            except Exception as e:
                st.session_state.errors.append(
                    (uploaded_file.name, f"Failed to write temp file: {e}")
                )

            progress_bar.progress((i + 1) / total)

        status_text.text(
            f"Done. {len(st.session_state.records)}/{total} file(s) succeeded."
        )
        st.session_state.processing = False

    # --- Sidebar ---
    _render_sidebar(st.session_state.records, st.session_state.errors)

    # --- Results section ---
    records = st.session_state.records
    if records:
        st.markdown("---")
        st.subheader("Results")

        # Metrics row
        col1, col2, col3 = st.columns(3)
        avg_score = sum(r.get("completeness_score", 0) for r in records) / len(records)
        col1.metric("Processed", len(records))
        col2.metric("Avg Completeness", f"{avg_score:.1f}%")
        col3.metric("Errors", len(st.session_state.errors))

        # Collect unique filter values
        all_seniorities = sorted({
            r.get("seniority_level", "") for r in records if r.get("seniority_level")
        })
        all_industries = sorted({
            ind
            for r in records
            for ind in (r.get("industries") or [])
        })

        fc1, fc2, fc3 = st.columns([1, 1, 2])
        seniority_filter = fc1.selectbox("Seniority", ["All"] + all_seniorities)
        industry_filter = fc2.selectbox("Industry", ["All"] + all_industries)
        name_filter = fc3.text_input("Search by name", placeholder="Jane Doe...")

        # Apply filters
        filtered = records
        if seniority_filter != "All":
            filtered = [r for r in filtered if r.get("seniority_level") == seniority_filter]
        if industry_filter != "All":
            filtered = [
                r for r in filtered if industry_filter in (r.get("industries") or [])
            ]
        if name_filter:
            name_lower = name_filter.lower()
            filtered = [
                r for r in filtered
                if name_lower in (r.get("full_name") or "").lower()
            ]

        # Results DataFrame
        st.dataframe(compile_results(filtered), use_container_width=True)

        # Per-record expanders
        st.markdown("---")
        for r in filtered:
            name = r.get("full_name") or "Unknown"
            seniority = r.get("seniority_level") or "—"
            score = r.get("completeness_score") or 0
            with st.expander(f"{name} · {seniority} · {score:.1f}%"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Email:** {r.get('email') or '—'}")
                    st.write(f"**Phone:** {r.get('phone') or '—'}")
                    st.write(f"**LinkedIn:** {r.get('linkedin_url') or '—'}")
                    st.write(f"**Location:** {r.get('location') or '—'}")
                    st.write(f"**Years of Experience:** {r.get('years_of_experience') or '—'}")
                with c2:
                    industries_list = r.get("industries") or []
                    pe_list = r.get("pe_firms") or []
                    st.write(f"**Industries:** {' | '.join(industries_list) or '—'}")
                    st.write(f"**PE Firms:** {' | '.join(pe_list) or 'None'}")
                    st.write(f"**Seniority:** {seniority}")
                    st.write(f"**Completeness:** {score:.1f}%")

                summary = r.get("profile_summary")
                if summary:
                    st.markdown(f"> {summary}")

                st.markdown("**Work History**")
                _render_work_history(r.get("_work_history") or [])

        # Download CSV + Send to Airtable
        st.markdown("---")
        dl_col, at_col = st.columns([1, 1])

        csv_bytes = compile_results(records).to_csv(index=False).encode("utf-8-sig")
        dl_col.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name="resume_results.csv",
            mime="text/csv",
        )

        if at_col.button("☁ Send to Airtable", key="airtable_btn"):
            with st.spinner(f"Sending {len(records)} record(s) to Airtable..."):
                try:
                    created, skipped, at_errors = push_records(records)
                    if created:
                        st.success(f"✓ {created} record(s) created in Airtable.")
                    if skipped:
                        st.info(f"⏭ {skipped} duplicate(s) skipped (email already exists).")
                    for err in at_errors:
                        st.error(err)
                except ValueError as e:
                    st.error(str(e))

    # --- Error display ---
    if st.session_state.errors:
        st.markdown("---")
        with st.expander(f"Errors ({len(st.session_state.errors)})"):
            for fname, msg in st.session_state.errors:
                st.error(f"**{fname}**: {msg}")


main()
