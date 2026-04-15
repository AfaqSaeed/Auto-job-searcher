"""Command-line interface for job_searcher."""

from __future__ import annotations

import argparse
from pathlib import Path

from job_searcher.pipeline import JobSearcherPipeline, PIPELINE_STAGES


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
    elif args.command == "run-all":
        pipeline.run_from(args.start_from, args.input, supplemental_files=args.resume)
    else:  # pragma: no cover - argparse prevents this
        parser.error(f"Unknown command: {args.command}")
    return 0
