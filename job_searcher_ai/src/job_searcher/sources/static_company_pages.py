"""Static company page connector."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from job_searcher.parsing.jobs import parse_static_job_page
from job_searcher.schemas import SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult
from job_searcher.utils.urls import join_url


class StaticCompanyPagesSource(BaseJobSource):
    name = "static_company_pages"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.static_pages:
            result.notes.append("no static company pages were configured")
            return result

        for page in context.config.sources.static_pages:
            html = context.get_text(page.url)
            if not html:
                continue
            if not page.job_card_selector:
                result.raw_jobs += 1
                job = parse_static_job_page(page.url, html, company=page.company)
                self.apply_query_filter(result, job, queries)
                continue

            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.select(page.job_card_selector)
            result.raw_jobs += len(cards)
            for card in cards:
                title_node = card.select_one(page.title_selector) if page.title_selector else card
                link_node = card.select_one(page.link_selector) if page.link_selector else card.find('a', href=True)
                link = join_url(page.url, link_node.get('href')) if link_node else page.url
                detail_html = context.get_text(link) if link != page.url else str(card)
                job = parse_static_job_page(link, detail_html, company=page.company)
                if title_node and job.title == 'Unknown title':
                    job.title = title_node.get_text(' ', strip=True)
                self.apply_query_filter(result, job, queries)

        result.diagnostics = context.take_diagnostics()
        return result
