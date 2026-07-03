"""Streamlit interface for explainable talent matching."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_searcher.config import load_config  # noqa: E402
from job_searcher.llm.ollama_client import OllamaClient  # noqa: E402
from job_searcher.matching.claim_checker import check_claim  # noqa: E402
from job_searcher.matching.evidence import build_candidate_evidence  # noqa: E402
from job_searcher.matching.service import build_candidate_match_report, build_manual_job_listing  # noqa: E402
from job_searcher.profile.extract import extract_profile  # noqa: E402
from job_searcher.profile.ingest import split_markdown_sections  # noqa: E402
from job_searcher.ranking.embeddings import EmbeddingBackend  # noqa: E402
from job_searcher.schemas import ProfileDocument  # noqa: E402


st.set_page_config(page_title="Explainable Talent Matching", layout="wide")


def _build_profile(profile_text: str):
    document = ProfileDocument(
        source_files=["streamlit_input"],
        raw_text=profile_text,
        sections=split_markdown_sections(profile_text),
    )
    return extract_profile(document)


def _build_client(config):
    if not config.ollama.enabled or not config.matching.use_llm:
        return None
    return OllamaClient(config.ollama)


def _claim_lines(raw_claims: str) -> list[str]:
    claims: list[str] = []
    for line in raw_claims.splitlines():
        cleaned = line.strip().lstrip("-* ").strip()
        if cleaned:
            claims.append(cleaned)
    return claims


config = load_config(project_root=ROOT)
client = _build_client(config)

tab_match, tab_evidence, tab_claims = st.tabs(
    ["Match Candidate to Role", "Inspect Requirement Evidence", "Check Application Claims"]
)

with tab_match:
    left, right = st.columns(2)
    with left:
        profile_text = st.text_area("Candidate profile text", height=420, key="profile_text")
    with right:
        job_text = st.text_area("Job description text", height=360, key="job_text")
        title = st.text_input("Title", key="job_title")
        company = st.text_input("Company", key="job_company")

    if st.button("Evaluate match", type="primary"):
        if not profile_text.strip() or not job_text.strip():
            st.warning("Profile and job description are required.")
        else:
            profile = _build_profile(profile_text)
            job = build_manual_job_listing(
                job_text,
                title=title or None,
                company=company or None,
                source="streamlit",
                source_url="streamlit_input",
            )
            report = build_candidate_match_report(
                profile=profile,
                job=job,
                config=config,
                client=client,
                raw_profile_text=profile_text,
            )
            st.session_state["match_report"] = report
            st.session_state["match_profile"] = profile
            st.session_state["match_evidence"] = build_candidate_evidence(profile, raw_profile_text=profile_text)

    report = st.session_state.get("match_report")
    if report:
        col_score, col_rec = st.columns([1, 3])
        col_score.metric("Overall score", f"{report.overall_score:.2f}")
        col_rec.write(report.recommendation)

        cols = st.columns(2)
        with cols[0]:
            st.subheader("Strengths")
            for item in report.strengths or ["No strengths identified from supplied evidence."]:
                st.write(f"- {item}")
        with cols[1]:
            st.subheader("Gaps")
            for item in report.gaps or ["No gaps identified from supplied evidence."]:
                st.write(f"- {item}")

        st.subheader("Requirement assessments")
        for assessment in report.assessments:
            with st.expander(f"{assessment.status.value}: {assessment.requirement}"):
                st.write(assessment.explanation)
                st.write(f"Confidence: {assessment.confidence:.2f}")
                if assessment.transferable_skills:
                    st.write(f"Transferable skills: {', '.join(assessment.transferable_skills)}")
                for item in assessment.evidence:
                    st.caption(f"{item.source_section} | similarity {item.similarity:.2f}")
                    st.write(item.text)

with tab_evidence:
    report = st.session_state.get("match_report")
    if not report:
        st.info("Run a match first.")
    else:
        for assessment in report.assessments:
            st.subheader(assessment.requirement)
            st.write(f"Status: {assessment.status.value}")
            st.write(assessment.explanation)
            st.write(f"Confidence: {assessment.confidence:.2f}")
            for item in assessment.evidence:
                st.caption(f"{item.source_section} | similarity {item.similarity:.2f}")
                st.write(item.text)

with tab_claims:
    raw_claims = st.text_area("Proposed application claims", height=220)
    if st.button("Check claims"):
        profile = st.session_state.get("match_profile")
        evidence = st.session_state.get("match_evidence")
        if profile is None or evidence is None:
            st.warning("Run a match first so the app can use the candidate profile evidence.")
        else:
            backend = EmbeddingBackend(config.embeddings.model_name, enabled=config.embeddings.enabled)
            for claim in _claim_lines(raw_claims):
                assessment = check_claim(claim, evidence, backend, client)
                status = "supported" if assessment.supported else "unsupported"
                with st.expander(f"{status}: {claim}", expanded=not assessment.supported):
                    st.write(assessment.explanation)
                    st.write(f"Confidence: {assessment.confidence:.2f}")
                    if assessment.safer_wording:
                        st.write(f"Safer wording: {assessment.safer_wording}")
                    for item in assessment.evidence:
                        st.caption(f"{item.source_section} | similarity {item.similarity:.2f}")
                        st.write(item.text)
