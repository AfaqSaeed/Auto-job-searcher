"""Logging helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path


LOGGER_NAME = "job_searcher"


def setup_logging(level: str | None = None, log_file: Path | None = None) -> logging.Logger:
    """Configure process-wide logging once and return the package logger."""

    resolved_level = getattr(logging, (level or os.getenv("JOB_SEARCHER_LOG_LEVEL", "INFO")).upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(LOGGER_NAME)
