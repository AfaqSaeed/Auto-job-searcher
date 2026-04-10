"""Custom career-page connector with same-domain crawling, sitemap fallback, and optional JS rendering."""

from __future__ import annotations

from collections import deque
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from job_searcher.config import CustomCareerPageConfig
from job_searcher.parsing.jobs import parse_static_job_page
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult
from job_searcher.utils.text import normalize_text
from job_searcher.utils.urls import domain_for_url, join_url


LOGGER = logging.getLogger(__name__)

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

FILTER_KIND_HINTS: dict[str, tuple[str, ...]] = {
    'search_text': ('search', 'keyword', 'query', 'suche'),
    'country_region': ('country', 'region', 'country / region', 'land'),
    'city_location': ('city', 'location', 'standort', 'ort'),
    'company': ('company', 'brand', 'unternehmen'),
    'category': ('category', 'department', 'function', 'bereich', 'job family', 'team'),
    'work_mode': ('remote', 'hybrid', 'onsite', 'arbeitsmodell'),
}


class CustomCareerPagesSource(BaseJobSource):
    name = 'custom_career_pages'

    def __init__(self) -> None:
        self._filter_snapshots: list[dict] = []

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        self._filter_snapshots = []
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
        if self._filter_snapshots:
            result.debug_data['filter_snapshots'] = list(self._filter_snapshots)
        result.diagnostics = context.take_diagnostics()
        return result

    def _discover_jobs_for_page(self, page: CustomCareerPageConfig, context: SourceContext) -> list[JobListing]:
        candidate_urls = self._collect_candidate_urls(page, context)
        LOGGER.info(
            'custom career page %s: static discovery produced %s candidate urls',
            page.name,
            len(candidate_urls),
        )
        if candidate_urls:
            LOGGER.info(
                'custom career page %s: static candidate sample: %s',
                page.name,
                candidate_urls[:3],
            )
        jobs = self._build_jobs_from_candidate_urls(candidate_urls, page, context)
        LOGGER.info(
            'custom career page %s: static candidate parsing produced %s jobs',
            page.name,
            len(jobs),
        )
        if jobs or not page.render_javascript:
            return jobs

        LOGGER.info(
            'custom career page %s: retrying with rendered DOM fallback using selector %s',
            page.name,
            page.rendered_link_selector or 'a[href]',
        )
        rendered_urls = self._collect_rendered_candidate_urls(page, domain_for_url(page.url), context)
        LOGGER.info(
            'custom career page %s: rendered discovery produced %s candidate urls',
            page.name,
            len(rendered_urls),
        )
        if rendered_urls:
            LOGGER.info(
                'custom career page %s: rendered candidate sample: %s',
                page.name,
                rendered_urls[:5],
            )
        rendered_jobs = self._build_jobs_from_candidate_urls(rendered_urls, page, context)
        LOGGER.info(
            'custom career page %s: rendered candidate parsing produced %s jobs',
            page.name,
            len(rendered_jobs),
        )
        return rendered_jobs

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
            deduped = self._dedupe_preserve_order(discovered)
            LOGGER.info(
                'custom career page %s: in-page crawl found %s candidate urls after dedupe',
                page.name,
                len(deduped),
            )
            return deduped

        sitemap_urls = self._collect_from_sitemaps(page, context)
        if sitemap_urls:
            deduped = self._dedupe_preserve_order(sitemap_urls)
            LOGGER.info(
                'custom career page %s: sitemap discovery found %s candidate urls after dedupe',
                page.name,
                len(deduped),
            )
            return deduped

        LOGGER.info(
            'custom career page %s: no candidate urls found from static crawl or sitemap fallback',
            page.name,
        )
        return []

    def _collect_from_sitemaps(self, page: CustomCareerPageConfig, context: SourceContext) -> list[str]:
        candidates: list[str] = []
        parsed = urlparse(page.url)
        root = f'{parsed.scheme}://{parsed.netloc}'
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
            LOGGER.warning(
                'custom career page %s: Playwright is unavailable for rendered fallback',
                page.name,
            )
            context.add_note_diagnostic(
                url=page.url,
                message='Playwright is not installed; install the browser extra and run playwright install chromium',
                kind='rendering_unavailable',
            )
            return []

        candidates: list[str] = []
        with sync_playwright() as playwright:
            LOGGER.info(
                'custom career page %s: launching Playwright rendered fallback',
                page.name,
            )
            browser = playwright.chromium.launch(headless=True)
            browser_page = browser.new_page()
            browser_page.set_default_timeout(context.config.scraping.request_timeout_seconds * 1000)
            try:
                render_urls = self._render_urls_for_page(page)
                LOGGER.info(
                    'custom career page %s: rendered fallback will try %s urls',
                    page.name,
                    render_urls,
                )
                for url in render_urls:
                    LOGGER.info(
                        'custom career page %s: rendering %s',
                        page.name,
                        url,
                    )
                    browser_page.goto(url, wait_until='networkidle')
                    html = browser_page.content()
                    self._capture_filter_snapshot(page, url, html)
                    if page.rendered_wait_selector:
                        try:
                            browser_page.wait_for_selector(page.rendered_wait_selector)
                            html = browser_page.content()
                            self._capture_filter_snapshot(page, url, html)
                        except PlaywrightTimeoutError:
                            context.add_note_diagnostic(
                                url=url,
                                message=f'render wait selector not found: {page.rendered_wait_selector}',
                                kind='rendering_timeout',
                            )
                    selector = page.rendered_link_selector or 'a[href]'
                    links = self._extract_links_by_selector(html, url, host, selector)
                    LOGGER.info(
                        'custom career page %s: rendered selector %s matched %s links on %s',
                        page.name,
                        selector,
                        len(links),
                        url,
                    )
                    if not links and selector != 'a[href]':
                        links = self._extract_links(html, url, host)
                        LOGGER.info(
                            'custom career page %s: fallback anchor scan matched %s links on %s',
                            page.name,
                            len(links),
                            url,
                        )
                    matching_links = [link for link in links if self._is_job_candidate_url(link, page)]
                    LOGGER.info(
                        'custom career page %s: %s rendered links survived URL pattern filtering on %s',
                        page.name,
                        len(matching_links),
                        url,
                    )
                    candidates.extend(matching_links)
            finally:
                browser.close()
        return candidates

    def _capture_filter_snapshot(self, page: CustomCareerPageConfig, url: str, html: str) -> None:
        fields = self._extract_filter_fields(html)
        if not fields:
            return
        snapshot = {
            'page_name': page.name,
            'url': url,
            'field_count': len(fields),
            'fields': fields,
        }
        if snapshot not in self._filter_snapshots:
            self._filter_snapshots.append(snapshot)
            LOGGER.info(
                'custom career page %s: captured %s rendered filter fields on %s',
                page.name,
                len(fields),
                url,
            )

    @staticmethod
    def _extract_filter_fields(html: str) -> list[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        fields: list[dict] = []

        for select in soup.find_all('select'):
            label = CustomCareerPagesSource._label_for_field(soup, select)
            options = [option.get_text(' ', strip=True) for option in select.find_all('option') if option.get_text(' ', strip=True)]
            if not options:
                continue
            fields.append(
                {
                    'name': select.get('name') or select.get('id') or label or 'select',
                    'label': label,
                    'type': 'multi_select' if select.has_attr('multiple') else 'select',
                    'semantic_kind': CustomCareerPagesSource._infer_filter_kind(select, label),
                    'options': options[:200],
                }
            )

        for input_node in soup.find_all('input'):
            input_type = (input_node.get('type') or 'text').lower()
            if input_type not in {'search', 'text', 'checkbox', 'radio'}:
                continue
            label = CustomCareerPagesSource._label_for_field(soup, input_node)
            placeholder = input_node.get('placeholder') or ''
            values: list[str] = []
            if input_type in {'checkbox', 'radio'}:
                values = [input_node.get('value') or label or placeholder]
            fields.append(
                {
                    'name': input_node.get('name') or input_node.get('id') or label or 'input',
                    'label': label or placeholder,
                    'type': input_type,
                    'semantic_kind': CustomCareerPagesSource._infer_filter_kind(input_node, label or placeholder),
                    'options': values,
                }
            )

        deduped: list[dict] = []
        seen: set[str] = set()
        for field in fields:
            key = f"{field['name']}::{field['type']}::{field.get('label', '')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(field)
        return deduped

    @staticmethod
    def _label_for_field(soup: BeautifulSoup, node) -> str:
        field_id = node.get('id')
        if field_id:
            label = soup.find('label', attrs={'for': field_id})
            if label:
                return label.get_text(' ', strip=True)
        parent_label = node.find_parent('label')
        if parent_label:
            return parent_label.get_text(' ', strip=True)
        aria_label = node.get('aria-label')
        if aria_label:
            return str(aria_label).strip()
        return ''

    @staticmethod
    def _infer_filter_kind(node, label: str) -> str:
        haystack = normalize_text(' '.join(filter(None, [label, node.get('name'), node.get('id'), node.get('placeholder')])))
        for kind, hints in FILTER_KIND_HINTS.items():
            if any(normalize_text(hint) in haystack for hint in hints):
                return kind
        return 'unknown'

    @staticmethod
    def _render_urls_for_page(page: CustomCareerPageConfig) -> list[str]:
        urls = [page.url, *page.seed_urls]
        base = page.url.rstrip('/')
        for pattern in page.include_url_patterns:
            normalized = pattern.strip().strip('/')
            if not normalized or '/' in normalized:
                continue
            urls.append(f'{base}/{normalized}')
        return CustomCareerPagesSource._dedupe_preserve_order(urls)

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
