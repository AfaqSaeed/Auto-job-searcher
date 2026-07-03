"""Command-line interface for job_searcher."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from job_searcher.matching.service import build_candidate_match_report, build_manual_job_listing
from job_searcher.pipeline import JobSearcherPipeline, PIPELINE_STAGES
from job_searcher.reporting.json_export import write_candidate_match_json
from job_searcher.reporting.markdown_report import build_candidate_match_markdown
from job_searcher.schemas import JobListing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job_searcher", description="Local-AI-assisted job search pipeline")
    parser.add_argument("--config", type=Path, default=None, help="Optional path to the YAML config file")
    parser.add_argument("--project-root", type=Path, default=None, help="Optional project root override")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-profile", help="Ingest and structure the main profile")
    ingest.add_argument("--input", type=Path, required=True, help="Main profile markdown or text file")
    ingest.add_argument("--resume", type=Path, nargs="*", default=[], help="Optional supplemental resume files")

    subparsers.add_parser("generate-queries", help="Generate job-search queries from the profile")
    subparsers.add_parser("discover-boards", help="Discover relevant companies and Greenhouse boards from the profile")
    subparsers.add_parser("search-jobs", help="Fetch jobs from enabled sources")
    subparsers.add_parser("rank-jobs", help="Rank discovered jobs against the profile")
    subparsers.add_parser("report", help="Render markdown and JSON reports")

    explain = subparsers.add_parser("explain-match", help="Explain one candidate-to-job match")
    explain.add_argument("--profile", type=Path, required=True, help="Candidate profile markdown or text file")
    explain.add_argument("--job", type=Path, required=True, help="Job JSON, Markdown, or text file")
    explain.add_argument("--claims", type=Path, default=None, help="Optional file with proposed application claims")
    explain.add_argument("--output", type=Path, default=None, help="Optional JSON output path")

    run_all = subparsers.add_parser("run-all", help="Execute the full pipeline")
    run_all.add_argument("--input", type=Path, required=True, help="Main profile markdown or text file")
    run_all.add_argument("--resume", type=Path, nargs="*", default=[], help="Optional supplemental resume files")
    run_all.add_argument(
        "--start-from",
        choices=PIPELINE_STAGES,
        default="ingest-profile",
        help="Start the pipeline from a particular stage instead of the beginning",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    pipeline = JobSearcherPipeline(project_root=args.project_root, config_path=args.config)

    if args.command == "ingest-profile":
        pipeline.ingest_profile(args.input, supplemental_files=args.resume)
    elif args.command == "generate-queries":
        pipeline.generate_queries()
    elif args.command == "discover-boards":
        pipeline.discover_job_boards()
    elif args.command == "search-jobs":
        pipeline.search_jobs()
    elif args.command == "rank-jobs":
        pipeline.rank_jobs()
    elif args.command == "report":
        pipeline.report()
    elif args.command == "explain-match":
        _run_explain_match(args, pipeline)
    elif args.command == "run-all":
        pipeline.run_from(args.start_from, args.input, supplemental_files=args.resume)
    else:  # pragma: no cover - argparse prevents this
        parser.error(f"Unknown command: {args.command}")
    return 0


def _run_explain_match(args: argparse.Namespace, pipeline: JobSearcherPipeline) -> None:
    profile_path = pipeline._resolve_path(args.profile)
    job_path = pipeline._resolve_path(args.job)
    claims_path = pipeline._resolve_path(args.claims) if args.claims else None
    output_path = pipeline._resolve_path(args.output) if args.output else pipeline.artifacts.explainable_match_report_json
    markdown_path = output_path.with_suffix(".md")
    if args.output is None:
        markdown_path = pipeline.artifacts.explainable_match_report_md

    profile = pipeline.ingest_profile(profile_path)
    raw_profile_text = profile_path.read_text(encoding="utf-8-sig")
    job = _read_job_listing(job_path)
    claims = _read_claims(claims_path) if claims_path else []

    report = build_candidate_match_report(
        profile=profile,
        job=job,
        config=pipeline.config,
        client=pipeline.llm_client,
        raw_profile_text=raw_profile_text,
        claims=claims,
    )
    write_candidate_match_json(report, output_path)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_candidate_match_markdown(report), encoding="utf-8")
    _print_match_summary(report, output_path, markdown_path)


def _read_job_listing(path: Path) -> JobListing:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict) and "listing" in payload and isinstance(payload["listing"], dict):
            payload = payload["listing"]
        if isinstance(payload, dict):
            try:
                return JobListing.model_validate(payload)
            except ValueError:
                return build_manual_job_listing(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    title=str(payload.get("title") or payload.get("job_title") or "Selected role"),
                    company=str(payload.get("company") or "Unknown company"),
                    location=payload.get("location"),
                    source="manual_json",
                    source_url=str(path),
                )
    return build_manual_job_listing(text, source="manual_file", source_url=str(path))


def _read_claims(path: Path) -> list[str]:
    claims: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        cleaned = line.strip().lstrip("-* ").strip()
        if cleaned and not cleaned.startswith("#"):
            claims.append(cleaned)
    return claims


def _print_match_summary(report, json_path: Path, markdown_path: Path) -> None:
    print(f"Match: {report.job_title} @ {report.company}")
    print(f"Overall score: {report.overall_score:.2f}")
    print(f"Recommendation: {report.recommendation}")
    if report.strengths:
        print("Top strengths:")
        for item in report.strengths[:3]:
            print(f"- {item}")
    if report.gaps:
        print("Top gaps:")
        for item in report.gaps[:3]:
            print(f"- {item}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
