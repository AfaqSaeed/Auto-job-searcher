"""Logging helpers."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


LOGGER_NAME = "job_searcher"


@contextmanager
def log_timed_operation(
    logger: logging.Logger,
    label: str,
    *,
    expected_seconds: float | None = None,
    heartbeat_seconds: float = 10.0,
) -> Iterator[None]:
    """Log start, elapsed heartbeats, and completion time for a long-running operation."""

    start = time.monotonic()
    stop_event = threading.Event()
    error: BaseException | None = None

    expectation_note = (
        f" Rough timeout/expected ceiling: {expected_seconds:.0f}s." if expected_seconds else " ETA is variable."
    )
    logger.info("%s started.%s", label, expectation_note)

    def _heartbeat() -> None:
        while not stop_event.wait(heartbeat_seconds):
            elapsed = time.monotonic() - start
            if expected_seconds is None:
                logger.info("%s still running after %.1fs.", label, elapsed)
                continue

            if elapsed <= expected_seconds:
                logger.info(
                    "%s still running after %.1fs (configured ceiling about %.0fs).",
                    label,
                    elapsed,
                    expected_seconds,
                )
            else:
                logger.info(
                    "%s still running after %.1fs (past configured ceiling of about %.0fs).",
                    label,
                    elapsed,
                    expected_seconds,
                )

    heartbeat_thread = threading.Thread(target=_heartbeat, name=f"timer:{label}", daemon=True)
    heartbeat_thread.start()
    try:
        yield
    except BaseException as exc:  # pragma: no cover - passthrough with logging
        error = exc
        raise
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=0.2)
        elapsed = time.monotonic() - start
        if error is None:
            logger.info("%s finished in %.1fs.", label, elapsed)
        else:
            logger.warning("%s failed after %.1fs.", label, elapsed)


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
