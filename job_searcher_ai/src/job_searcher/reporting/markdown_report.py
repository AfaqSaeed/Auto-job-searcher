"""Markdown report rendering."""

from __future__ import annotations

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
        f"- Jobs discovered: {report.total_jobs_discovered}",
        f"- Jobs ranked: {report.total_jobs_ranked}",
        "",
        "## Profile Summary",
        report.profile_summary or "No summary available.",
        "",
        "## Query Samples",
    ]
    for query in report.queries[:15]:
        lines.append(f"- {query.text} ({query.rationale or 'generated'})")
    lines.extend(["", "## Top Jobs"])
    for item in report.top_jobs[:10]:
        lines.append(f"- {item.listing.title} @ {item.listing.company}: {item.score.overall_score} [{item.score.disposition.value}]")
    if report.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines).strip() + "\n"
