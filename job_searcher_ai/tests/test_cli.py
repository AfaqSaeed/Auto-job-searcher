from job_searcher.cli import build_parser


def test_run_all_parser_accepts_start_from() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            'run-all',
            '--input',
            'data/profile_master.md',
            '--start-from',
            'search-jobs',
        ]
    )

    assert args.command == 'run-all'
    assert args.start_from == 'search-jobs'


def test_explain_match_parser_accepts_paths() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "explain-match",
            "--profile",
            "examples/sample_candidate_profile.md",
            "--job",
            "examples/sample_job_description.txt",
            "--claims",
            "examples/sample_claims.txt",
            "--output",
            "outputs/custom_match.json",
        ]
    )

    assert args.command == "explain-match"
    assert args.profile.as_posix() == "examples/sample_candidate_profile.md"
    assert args.job.as_posix() == "examples/sample_job_description.txt"
