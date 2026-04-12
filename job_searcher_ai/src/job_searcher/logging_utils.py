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


class ProgressLogger:
    """Log progress with elapsed time and a simple ETA based on observed throughput."""

    def __init__(
        self,
        logger: logging.Logger,
        label: str,
        total: int,
        *,
        min_interval_seconds: float = 5.0,
    ) -> None:
        self.logger = logger
        self.label = label
        self.total = max(total, 0)
        self.min_interval_seconds = min_interval_seconds
        self.start = time.monotonic()
        self.last_logged_at = self.start
        self.completed = 0
        self.logger.info("%s progress started: 0/%s done.", self.label, self.total)

    def advance(self, step: int = 1) -> None:
        if self.total <= 0:
            return
        self.completed = min(self.total, self.completed + step)
        now = time.monotonic()
        should_log = (
            self.completed == self.total
            or self.completed == 1
            or now - self.last_logged_at >= self.min_interval_seconds
        )
        if not should_log:
            return
        self.last_logged_at = now
        elapsed = max(now - self.start, 0.001)
        rate = self.completed / elapsed
        remaining = max(self.total - self.completed, 0)
        eta_seconds = remaining / rate if rate > 0 else None
        if eta_seconds is None:
            self.logger.info(
                "%s progress: %s/%s done after %.1fs.",
                self.label,
                self.completed,
                self.total,
                elapsed,
            )
            return
        self.logger.info(
            "%s progress: %s/%s done after %.1fs, rough ETA %.1fs.",
            self.label,
            self.completed,
            self.total,
            elapsed,
            eta_seconds,
        )

    def finish(self) -> None:
        if self.total <= 0:
            self.logger.info("%s progress finished: no work items.", self.label)
            return
        self.completed = self.total
        elapsed = time.monotonic() - self.start
        self.logger.info("%s progress finished: %s/%s done in %.1fs.", self.label, self.completed, self.total, elapsed)


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
