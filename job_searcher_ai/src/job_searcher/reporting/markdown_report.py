"""Markdown report rendering."""

from __future__ import annotations

from job_searcher.matching.schemas import CandidateMatchReport
from job_searcher.schemas import RankedJob, SearchReport


def build_top_matches_markdown(ranked_jobs: list[RankedJob], top_n: int = 20) -> str:
    """Render the top matches list."""

    lines = ["# Top Matches", ""]
    for index, item in enumerate(ranked_jobs[:top_n], start=1):
        lines.extend(
            [
                f"## {index}. {item.listing.title} @ {item.listing.company}",
                f"- Score: {item.score.overall_score}",
                f"- Disposition: {item.score.disposition.value}",
                f"- Location: {item.listing.location or 'Unknown'} | Work mode: {item.listing.work_mode.value}",
                f"- Source: {item.listing.source}",
                f"- Why it matches: {item.score.why_match}",
                f"- Missing skills: {', '.join(item.score.missing_skills) or 'None flagged'}",
                f"- Resume emphasis: {item.score.recommended_resume_emphasis}",
                f"- Cover-letter angle: {item.score.recommended_cover_letter_angle}",
                f"- Apply URL: {item.listing.application_url or item.listing.source_url}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_search_report_markdown(report: SearchReport) -> str:
    """Render a search-report markdown summary."""

    lines = [
        "# Search Report",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Sources searched: {', '.join(report.sources_searched) or 'None'}",
        f"- Queries generated: {len(report.queries)}",
        f"- Raw jobs discovered: {report.total_jobs_raw_discovered}",
        f"- Jobs filtered out: {report.total_jobs_filtered_out}",
        f"- Jobs matched after filtering: {report.total_jobs_discovered}",
        f"- Jobs ranked: {report.total_jobs_ranked}",
        "",
        "## Profile Summary",
        report.profile_summary or "No summary available.",
        "",
        "## Query Samples",
    ]
    for query in report.queries[:15]:
        lines.append(f"- {query.text} ({query.rationale or 'generated'})")
    if report.source_stats:
        lines.extend(["", "## Source Stats"])
        for stats in report.source_stats:
            lines.append(
                f"- {stats.source_name}: raw {stats.raw_jobs_discovered}, filtered {stats.jobs_filtered_out}, matched {stats.jobs_matched}"
            )
    lines.extend(["", "## Top Jobs"])
    for item in report.top_jobs[:10]:
        lines.append(f"- {item.listing.title} @ {item.listing.company}: {item.score.overall_score} [{item.score.disposition.value}]")
    if report.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines).strip() + "\n"


def build_candidate_match_markdown(report: CandidateMatchReport) -> str:
    """Render an explainable match report as Markdown."""

    lines = [
        f"# Explainable Match Report: {report.job_title} @ {report.company}",
        "",
        f"- Candidate: {report.candidate_name or 'Unknown'}",
        f"- Overall score: {report.overall_score:.2f}",
        f"- Recommendation: {report.recommendation}",
        "",
        "## Strengths",
    ]
    lines.extend(_bullet_list(report.strengths, empty="No strengths identified from supplied evidence."))
    lines.extend(["", "## Gaps"])
    lines.extend(_bullet_list(report.gaps, empty="No gaps identified from supplied evidence."))

    lines.extend(["", "## Requirement Assessments"])
    if not report.assessments:
        lines.append("No requirements were extracted for this job.")
    for assessment in report.assessments:
        lines.extend(
            [
                "",
                f"### {assessment.requirement}",
                f"- Status: {assessment.status.value}",
                f"- Confidence: {assessment.confidence:.2f}",
                f"- Explanation: {assessment.explanation}",
            ]
        )
        if assessment.transferable_skills:
            lines.append(f"- Transferable skills: {', '.join(assessment.transferable_skills)}")
        lines.append("- Evidence:")
        if assessment.evidence:
            for item in assessment.evidence:
                lines.append(
                    f"  - [{item.source_section}] similarity {item.similarity:.2f}: {_excerpt(item.text)}"
                )
        else:
            lines.append("  - None supplied.")

    lines.extend(["", "## Unsupported Claims"])
    if not report.unsupported_claims:
        lines.append("No unsupported claims were flagged.")
    for claim in report.unsupported_claims:
        lines.extend(
            [
                "",
                f"### {claim.claim}",
                f"- Supported: {str(claim.supported).lower()}",
                f"- Confidence: {claim.confidence:.2f}",
                f"- Explanation: {claim.explanation}",
            ]
        )
        if claim.safer_wording:
            lines.append(f"- Safer wording: {claim.safer_wording}")
        lines.append("- Evidence:")
        if claim.evidence:
            for item in claim.evidence:
                lines.append(
                    f"  - [{item.source_section}] similarity {item.similarity:.2f}: {_excerpt(item.text)}"
                )
        else:
            lines.append("  - None supplied.")
    return "\n".join(lines).strip() + "\n"


def _bullet_list(values: list[str], empty: str) -> list[str]:
    if not values:
        return [f"- {empty}"]
    return [f"- {value}" for value in values]


def _excerpt(value: str, limit: int = 280) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."
