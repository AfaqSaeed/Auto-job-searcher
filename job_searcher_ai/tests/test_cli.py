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
