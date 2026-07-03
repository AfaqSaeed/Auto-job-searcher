"""JSON export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from job_searcher.matching.schemas import CandidateMatchReport


def write_json_output(payload: Any, output_path: Path) -> None:
    """Write JSON with stable formatting."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_candidate_match_json(report: CandidateMatchReport, output_path: Path) -> None:
    """Write an explainable match report as JSON."""

    write_json_output(report.model_dump(mode="json"), output_path)
