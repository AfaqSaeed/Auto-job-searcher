"""Job source connectors."""

from __future__ import annotations

from pathlib import Path

from job_searcher.config import AppConfig
from job_searcher.sources.base import BaseJobSource
from job_searcher.sources.greenhouse import GreenhouseSource
from job_searcher.sources.lever import LeverSource
from job_searcher.sources.manual_import import ManualImportSource
from job_searcher.sources.rss import RSSSource
from job_searcher.sources.static_company_pages import StaticCompanyPagesSource


def build_enabled_sources(config: AppConfig, project_root: Path) -> list[BaseJobSource]:
    sources: list[BaseJobSource] = []
    toggles = config.sources.toggles
    if toggles.greenhouse:
        sources.append(GreenhouseSource())
    if toggles.lever:
        sources.append(LeverSource())
    if toggles.static_pages:
        sources.append(StaticCompanyPagesSource(project_root))
    if toggles.rss:
        sources.append(RSSSource())
    if toggles.manual_import:
        sources.append(ManualImportSource(project_root))
    return sources
