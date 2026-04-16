"""Custom career-page connector with same-domain crawling, sitemap fallback, and optional JS rendering."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from job_searcher.config import CustomCareerPageConfig
from job_searcher.logging_utils import ProgressLogger
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
        self._site_filter_jobs: list[JobListing] = []

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        self._filter_snapshots = []
        self._site_filter_jobs = []
        result = SourceRunResult(source_name=self.name)
        pages = context.config.sources.custom_career_pages
        if not pages:
            result.notes.append('no custom career pages were configured')
            return result

        page_progress = ProgressLogger(LOGGER, "Custom career pages", len(pages), min_interval_seconds=3.0)
        for page in pages:
            page_result = SourceRunResult(source_name=self.name)
            self._discover_jobs_for_page(page, context, queries, page_result)
            if not page_result.discovered_jobs:
                result.notes.append(f"{page.name}: no candidate job detail pages were discovered")
                page_progress.advance()
                continue
            result.merge_from(page_result)
            context.maybe_checkpoint(result, force=True)
            page_progress.advance()
        page_progress.finish()
        if self._filter_snapshots:
            result.debug_data['filter_snapshots'] = list(self._filter_snapshots)
        if self._site_filter_jobs:
            result.debug_data['site_filter_jobs'] = [job.model_dump(mode='json') for job in self._site_filter_jobs]
        result.diagnostics = context.take_diagnostics()
        return result

    def _discover_jobs_for_page(
        self,
        page: CustomCareerPageConfig,
        context: SourceContext,
        queries: list[SearchQuery],
        result: SourceRunResult,
    ) -> None:
        seen_urls: set[str] = {job.source_url for job in result.discovered_jobs}

        def record_job(job: JobListing) -> None:
            if job.source_url in seen_urls:
                return
            seen_urls.add(job.source_url)
            result.raw_jobs += 1
            result.discovered_jobs.append(job)
            self.apply_query_filter(result, job, queries)
            context.maybe_checkpoint(result)

        jobs: list[JobListing] = []
        if page.discovery_strategy != 'site_filters_only':
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
            jobs = self._build_jobs_from_candidate_urls(candidate_urls, page, context, on_job=record_job)
            LOGGER.info(
                'custom career page %s: static candidate parsing produced %s jobs',
                page.name,
                len(jobs),
            )

        if page.render_javascript and not jobs and page.discovery_strategy != 'site_filters_only':
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
            rendered_jobs = self._build_jobs_from_candidate_urls(rendered_urls, page, context, on_job=record_job)
            LOGGER.info(
                'custom career page %s: rendered candidate parsing produced %s jobs',
                page.name,
                len(rendered_jobs),
            )

        if page.render_javascript and page.apply_site_filters:
            filtered_urls = self._collect_site_filtered_candidate_urls(page, context, queries)
            LOGGER.info(
                'custom career page %s: site-filter execution produced %s candidate urls',
                page.name,
                len(filtered_urls),
            )
            if filtered_urls:
                LOGGER.info(
                    'custom career page %s: site-filter candidate sample: %s',
                    page.name,
                    filtered_urls[:5],
                )
            filtered_jobs = self._build_jobs_from_candidate_urls(
                filtered_urls,
                page,
                context,
                extra_raw_payload={"discovery_method": "site_filter"},
                on_job=record_job,
            )
            self._site_filter_jobs = self._merge_jobs(self._site_filter_jobs, filtered_jobs)
            LOGGER.info(
                'custom career page %s: site-filter candidate parsing produced %s jobs',
                page.name,
                len(filtered_jobs),
            )

    def _build_jobs_from_candidate_urls(
        self,
        candidate_urls: list[str],
        page: CustomCareerPageConfig,
        context: SourceContext,
        extra_raw_payload: dict | None = None,
        on_job: Callable[[JobListing], None] | None = None,
    ) -> list[JobListing]:
        jobs: list[JobListing] = []
        ordered_urls: list[str] = []
        seen_urls: set[str] = set()
        for url in candidate_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            ordered_urls.append(url)

        if not ordered_urls:
            return jobs

        progress = ProgressLogger(
            LOGGER,
            f"Custom page {page.name} candidate pages",
            len(ordered_urls),
            min_interval_seconds=3.0,
        )
        workers = max(1, page.candidate_parse_workers)

        def parse_candidate(url: str) -> JobListing | None:
            html = context.get_text(url)
            if not html:
                return None
            job = parse_static_job_page(url, html, company=page.company or page.name, source=self.name)
            job.raw_payload.update(
                {
                    'custom_page_name': page.name,
                    'discovery_url': page.url,
                }
            )
            if extra_raw_payload:
                job.raw_payload.update(extra_raw_payload)
            if not self._looks_like_job(job, html):
                return None
            return job

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(parse_candidate, url): url for url in ordered_urls}
            for future in as_completed(futures):
                job = future.result()
                if job is not None:
                    jobs.append(job)
                    if on_job is not None:
                        on_job(job)
                progress.advance()
        progress.finish()
        return jobs

    @staticmethod
    def _merge_jobs(existing: list[JobListing], incoming: list[JobListing]) -> list[JobListing]:
        seen = {job.source_url for job in existing}
        merged = list(existing)
        for job in incoming:
            if job.source_url in seen:
                continue
            seen.add(job.source_url)
            merged.append(job)
        return merged

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
                render_progress = ProgressLogger(
                    LOGGER,
                    f"Custom page {page.name} rendered URLs",
                    len(render_urls),
                    min_interval_seconds=3.0,
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
                    render_progress.advance()
                render_progress.finish()
            finally:
                browser.close()
        return candidates

    def _collect_site_filtered_candidate_urls(
        self,
        page: CustomCareerPageConfig,
        context: SourceContext,
        queries: list[SearchQuery],
    ) -> list[str]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            LOGGER.warning(
                'custom career page %s: Playwright is unavailable for site-filter execution',
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
            browser = playwright.chromium.launch(headless=True)
            browser_page = browser.new_page()
            browser_page.set_default_timeout(context.config.scraping.request_timeout_seconds * 1000)
            try:
                render_urls = self._render_urls_for_page(page)
                render_progress = ProgressLogger(
                    LOGGER,
                    f"Custom page {page.name} site-filter URLs",
                    len(render_urls),
                    min_interval_seconds=3.0,
                )
                for url in render_urls:
                    browser_page.goto(url, wait_until='networkidle')
                    html = browser_page.content()
                    self._capture_filter_snapshot(page, url, html)
                    if page.rendered_wait_selector:
                        try:
                            browser_page.wait_for_selector(page.rendered_wait_selector)
                            html = browser_page.content()
                            self._capture_filter_snapshot(page, url, html)
                        except PlaywrightTimeoutError:
                            continue
                    fields = self._extract_filter_fields(html)
                    plans = self._derive_filter_plans(fields, page, context.config, queries)
                    LOGGER.info(
                        'custom career page %s: derived %s site-filter plans on %s',
                        page.name,
                        len(plans),
                        url,
                    )
                    if plans:
                        LOGGER.info(
                            'custom career page %s: site-filter plan sample on %s: %s',
                            page.name,
                            url,
                            plans[:3],
                        )
                    plan_progress = ProgressLogger(
                        LOGGER,
                        f"Custom page {page.name} filter plans on {url}",
                        len(plans),
                        min_interval_seconds=3.0,
                    )
                    for plan in plans:
                        browser_page.goto(url, wait_until='networkidle')
                        if page.rendered_wait_selector:
                            try:
                                browser_page.wait_for_selector(page.rendered_wait_selector)
                            except PlaywrightTimeoutError:
                                continue
                        self._apply_filter_plan(browser_page, fields, plan)
                        current_html = browser_page.content()
                        self._capture_filter_snapshot(page, url, current_html)
                        selector = page.rendered_link_selector or 'a[href]'
                        host = domain_for_url(url)
                        links = self._extract_links_by_selector(current_html, url, host, selector)
                        if not links and selector != 'a[href]':
                            links = self._extract_links(current_html, url, host)
                        matching_links = [link for link in links if self._is_job_candidate_url(link, page)]
                        LOGGER.info(
                            'custom career page %s: plan %s produced %s matching links on %s',
                            page.name,
                            plan,
                            len(matching_links),
                            url,
                        )
                        candidates.extend(matching_links)
                        plan_progress.advance()
                        if len(candidates) >= page.max_site_filter_candidate_urls:
                            break
                    plan_progress.finish()
                    render_progress.advance()
                    if len(candidates) >= page.max_site_filter_candidate_urls:
                        LOGGER.info(
                            'custom career page %s: stopping site-filter collection at configured limit of %s urls',
                            page.name,
                            page.max_site_filter_candidate_urls,
                        )
                        break
                render_progress.finish()
            finally:
                browser.close()
        deduped = self._dedupe_preserve_order(candidates)
        return deduped[: page.max_site_filter_candidate_urls]

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
                    'selector': CustomCareerPagesSource._selector_for_node(select),
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
                    'selector': CustomCareerPagesSource._selector_for_node(input_node),
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
    def _selector_for_node(node) -> str | None:
        field_id = node.get('id')
        if field_id:
            return f"#{field_id}"
        name = node.get('name')
        if name:
            return f"{node.name}[name='{name}']"
        return None

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
    def _derive_filter_plans(
        fields: list[dict],
        page: CustomCareerPageConfig,
        config,
        queries: list[SearchQuery],
    ) -> list[dict[str, str]]:
        if not fields:
            return []
        field_by_kind = {field['semantic_kind']: field for field in fields if field.get('semantic_kind') != 'unknown'}
        base_plan: dict[str, str] = {}

        country_field = field_by_kind.get('country_region')
        if country_field:
            country_value = CustomCareerPagesSource._first_option_match(
                country_field.get('options', []),
                config.search.target_countries,
            )
            if country_value:
                base_plan['country_region'] = country_value

        company_field = field_by_kind.get('company')
        if company_field and page.company:
            company_value = CustomCareerPagesSource._first_option_match(company_field.get('options', []), [page.company])
            if company_value:
                base_plan['company'] = company_value

        category_field = field_by_kind.get('category')
        category_candidates = config.search.job_titles + config.search.include_keywords
        if category_field:
            category_value = CustomCareerPagesSource._first_option_match(category_field.get('options', []), category_candidates)
            if category_value:
                base_plan['category'] = category_value

        plans: list[dict[str, str]] = []
        if base_plan:
            plans.append(dict(base_plan))

        search_field = field_by_kind.get('search_text')
        if search_field:
            for term in CustomCareerPagesSource._search_terms_for_site_filters(config, queries)[:6]:
                plan = dict(base_plan)
                plan['search_text'] = term
                plans.append(plan)

        deduped: list[dict[str, str]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for plan in plans:
            key = tuple(sorted(plan.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(plan)
        return deduped[: page.max_site_filter_plans]

    @staticmethod
    def _search_terms_for_site_filters(config, queries: list[SearchQuery]) -> list[str]:
        terms: list[str] = []
        terms.extend(config.search.job_titles)
        terms.extend(config.search.include_keywords)
        for query in queries:
            if query.title:
                terms.append(query.title)
            terms.extend(query.terms)
            if len(query.text.split()) <= 4:
                terms.append(query.text)
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            cleaned = term.strip()
            normalized = normalize_text(cleaned)
            if not cleaned or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(cleaned)
        return deduped

    @staticmethod
    def _first_option_match(options: list[str], desired_values: list[str]) -> str | None:
        normalized_options = [(option, normalize_text(option)) for option in options]
        for desired in desired_values:
            desired_normalized = normalize_text(desired)
            for option, option_normalized in normalized_options:
                if desired_normalized == option_normalized or desired_normalized in option_normalized or option_normalized in desired_normalized:
                    return option
        return None

    @staticmethod
    def _apply_filter_plan(browser_page, fields: list[dict], plan: dict[str, str]) -> None:
        for semantic_kind, desired_value in plan.items():
            field = next((item for item in fields if item.get('semantic_kind') == semantic_kind and item.get('selector')), None)
            if not field:
                continue
            selector = field['selector']
            try:
                if field['type'] in {'select', 'multi_select'}:
                    browser_page.locator(selector).select_option(label=desired_value)
                elif field['type'] in {'search', 'text'}:
                    locator = browser_page.locator(selector)
                    locator.fill('')
                    locator.fill(desired_value)
                    locator.press('Enter')
                elif field['type'] in {'checkbox', 'radio'}:
                    browser_page.locator(selector).check()
            except Exception:
                continue
        try:
            browser_page.wait_for_load_state('networkidle')
        except Exception:
            pass

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
