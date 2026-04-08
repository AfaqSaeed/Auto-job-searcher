"""JSON export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_output(payload: Any, output_path: Path) -> None:
    """Write JSON with stable formatting."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
