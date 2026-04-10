"""Custom career-page connector with same-domain crawling, sitemap fallback, and optional JS rendering."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from job_searcher.config import CustomCareerPageConfig
from job_searcher.parsing.jobs import parse_static_job_page
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult
from job_searcher.utils.urls import domain_for_url, join_url

if TYPE_CHECKING:
    from playwright.sync_api import Page


DEFAULT_JOB_HINTS = (
    'job',
    'jobs',
    'career',
    'careers',
    'vacanc',
    'opening',
    'position',
    'stellen',
    'jobsearch',
)


class CustomCareerPagesSource(BaseJobSource):
    name = 'custom_career_pages'

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        pages = context.config.sources.custom_career_pages
        if not pages:
            result.notes.append('no custom career pages were configured')
            return result

        for page in pages:
            discovered = self._discover_jobs_for_page(page, context)
            if not discovered:
                result.notes.append(f"{page.name}: no candidate job detail pages were discovered")
                continue
            result.raw_jobs += len(discovered)
            result.discovered_jobs.extend(discovered)
            for job in discovered:
                if self.matches_queries(job, queries):
                    result.jobs.append(job)
                    result.matched_jobs += 1
                else:
                    result.filtered_out_jobs.append(job)
        result.diagnostics = context.take_diagnostics()
        return result

    def _discover_jobs_for_page(self, page: CustomCareerPageConfig, context: SourceContext) -> list[JobListing]:
        candidate_urls = self._collect_candidate_urls(page, context)
        jobs = self._build_jobs_from_candidate_urls(candidate_urls, page, context)
        if jobs or not page.render_javascript:
            return jobs

        rendered_urls = self._collect_rendered_candidate_urls(page, domain_for_url(page.url), context)
        return self._build_jobs_from_candidate_urls(rendered_urls, page, context)

    def _build_jobs_from_candidate_urls(
        self,
        candidate_urls: list[str],
        page: CustomCareerPageConfig,
        context: SourceContext,
    ) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_urls: set[str] = set()
        for url in candidate_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            html = context.get_text(url)
            if not html:
                continue
            job = parse_static_job_page(url, html, company=page.company or page.name, source=self.name)
            job.raw_payload.update(
                {
                    'custom_page_name': page.name,
                    'discovery_url': page.url,
                }
            )
            if not self._looks_like_job(job, html):
                continue
            jobs.append(job)
        return jobs

    def _collect_candidate_urls(self, page: CustomCareerPageConfig, context: SourceContext) -> list[str]:
        queue = deque([page.url, *page.seed_urls])
        discovered: list[str] = []
        visited: set[str] = set()
        host = domain_for_url(page.url)

        while queue and len(visited) < page.max_pages:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            html = context.get_text(current)
            if not html:
                continue
            for link in self._extract_links(html, current, host):
                if link in visited:
                    continue
                if self._is_job_candidate_url(link, page):
                    discovered.append(link)
                elif self._is_within_scope(link, host, page):
                    queue.append(link)

        if discovered:
            return self._dedupe_preserve_order(discovered)

        sitemap_urls = self._collect_from_sitemaps(page, context)
        if sitemap_urls:
            return self._dedupe_preserve_order(sitemap_urls)

        return []

    def _collect_from_sitemaps(self, page: CustomCareerPageConfig, context: SourceContext) -> list[str]:
        candidates: list[str] = []
        parsed = urlparse(page.url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        for path in page.sitemap_paths:
            sitemap_url = join_url(root, path)
            xml_text = context.get_text(sitemap_url)
            if not xml_text:
                continue
            for loc in self._parse_sitemap_locations(xml_text):
                if self._is_job_candidate_url(loc, page):
                    candidates.append(loc)
        return candidates

    def _collect_rendered_candidate_urls(
        self,
        page: CustomCareerPageConfig,
        host: str,
        context: SourceContext,
    ) -> list[str]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            context.add_note_diagnostic(
                url=page.url,
                message='Playwright is not installed; install the browser extra and run playwright install chromium',
                kind='rendering_unavailable',
            )
            return []

        candidates: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser_page = browser.new_page()
            browser_page.set_default_timeout(context.config.scraping.request_timeout_seconds * 1000)
            try:
                for url in [page.url, *page.seed_urls]:
                    browser_page.goto(url, wait_until='networkidle')
                    if page.rendered_wait_selector:
                        try:
                            browser_page.wait_for_selector(page.rendered_wait_selector)
                        except PlaywrightTimeoutError:
                            context.add_note_diagnostic(
                                url=url,
                                message=f'render wait selector not found: {page.rendered_wait_selector}',
                                kind='rendering_timeout',
                            )
                    selector = page.rendered_link_selector or 'a[href]'
                    html = browser_page.content()
                    links = self._extract_links_by_selector(html, url, host, selector)
                    if not links and selector != 'a[href]':
                        links = self._extract_links(html, url, host)
                    candidates.extend(link for link in links if self._is_job_candidate_url(link, page))
            finally:
                browser.close()
        return candidates

    @staticmethod
    def _extract_links(html: str, base_url: str, host: str) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        links: list[str] = []
        for anchor in soup.find_all('a', href=True):
            href = join_url(base_url, anchor.get('href'))
            if domain_for_url(href) != host:
                continue
            links.append(href.split('#', 1)[0])
        return links

    @staticmethod
    def _extract_links_by_selector(html: str, base_url: str, host: str, selector: str) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        links: list[str] = []
        for node in soup.select(selector):
            href = node.get('href')
            if not href:
                continue
            url = join_url(base_url, href)
            if domain_for_url(url) != host:
                continue
            links.append(url.split('#', 1)[0])
        return links

    @staticmethod
    def _parse_sitemap_locations(xml_text: str) -> list[str]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return []
        locations: list[str] = []
        for element in root.iter():
            if element.tag.endswith('loc') and element.text:
                locations.append(element.text.strip())
        return locations

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    @staticmethod
    def _looks_like_job(job: JobListing, html: str) -> bool:
        title = job.title.lower().strip()
        text = (job.description or '').lower()
        if title in {'unknown title', 'vacancies', 'careers', 'stellenangebote'}:
            return False
        if len(text) < 120:
            return False
        return any(hint in text or hint in title for hint in DEFAULT_JOB_HINTS + ('responsibilities', 'qualifications', 'apply'))

    @staticmethod
    def _is_within_scope(url: str, host: str, page: CustomCareerPageConfig) -> bool:
        if domain_for_url(url) != host:
            return False
        lowered = url.lower()
        if any(pattern.lower() in lowered for pattern in page.exclude_url_patterns):
            return False
        return True

    @staticmethod
    def _is_job_candidate_url(url: str, page: CustomCareerPageConfig) -> bool:
        lowered = url.lower()
        if any(pattern.lower() in lowered for pattern in page.exclude_url_patterns):
            return False
        if page.include_url_patterns:
            return any(pattern.lower() in lowered for pattern in page.include_url_patterns)
        return any(hint in lowered for hint in DEFAULT_JOB_HINTS)
