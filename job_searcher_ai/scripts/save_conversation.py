"""Save a markdown conversation archive to disk."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save a conversation summary or transcript to a markdown file.")
    parser.add_argument("--output", type=Path, required=True, help="Target markdown file path")
    parser.add_argument("--title", default="Conversation Archive", help="Document title")
    parser.add_argument("--content-file", type=Path, default=None, help="Optional path to a markdown or text file to copy")
    parser.add_argument("--body", default=None, help="Optional inline markdown body")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.content_file is not None:
        body = args.content_file.read_text(encoding="utf-8")
    elif args.body is not None:
        body = args.body
    else:
        body = "No conversation body was provided."

    timestamp = datetime.utcnow().isoformat()
    output = f"# {args.title}\n\n- Saved at: {timestamp}Z\n\n{body.strip()}\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
