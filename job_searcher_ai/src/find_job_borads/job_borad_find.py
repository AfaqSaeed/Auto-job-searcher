"""Compatibility wrapper for the misspelled board finder entrypoint."""

from __future__ import annotations

from jobs_board_find_multi import main


if __name__ == "__main__":
    raise SystemExit(main())
