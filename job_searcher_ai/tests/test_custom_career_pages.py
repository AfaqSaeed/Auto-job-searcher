from job_searcher.config import AppConfig, CustomCareerPageConfig
from job_searcher.schemas import SearchQuery
from job_searcher.sources.custom_career_pages import CustomCareerPagesSource


class FakeCache:
    def get(self, key: str, ttl_hours: int | None = None):
        return None

    def set(self, key: str, value) -> None:
        return None


class FakeContext:
    def __init__(self, html_map: dict[str, str], page_config: CustomCareerPageConfig | None = None) -> None:
        self.config = AppConfig()
        self.config.sources.custom_career_pages = [
            page_config
            or CustomCareerPageConfig(
                name='Example Careers',
                company='Example Robotics',
                url='https://example.com/careers',
                include_url_patterns=['/jobs/'],
            )
        ]
        self.cache = FakeCache()
        self._html_map = html_map
        self._diagnostics = []

    def set_active_source(self, source_name: str) -> None:
        self._diagnostics = []

    def get_text(self, url: str) -> str:
        return self._html_map.get(url, '')

    def take_diagnostics(self):
        diagnostics = list(self._diagnostics)
        self._diagnostics = []
        return diagnostics

    def add_note_diagnostic(self, *, url: str, message: str, kind: str, status_code: int | None = None) -> None:
        self._diagnostics.append({'url': url, 'message': message, 'kind': kind, 'status_code': status_code})


class RenderedSource(CustomCareerPagesSource):
    def __init__(self, rendered_urls: list[str]) -> None:
        self._rendered_urls = rendered_urls

    def _collect_rendered_candidate_urls(self, page, host, context):
        return list(self._rendered_urls)


def test_custom_career_pages_fetches_and_filters_jobs() -> None:
    landing = '<html><body><a href="/jobs/vision-engineer">Vision Engineer</a><a href="/about">About</a></body></html>'
    detail = '<html><head><title>Vision Engineer</title></head><body><h1>Vision Engineer</h1><div class="location">Augsburg, Germany</div><p>Responsibilities include computer vision, robotics, perception, and deployment work.</p><p>Apply now</p></body></html>'
    context = FakeContext(
        {
            'https://example.com/careers': landing,
            'https://example.com/jobs/vision-engineer': detail,
            'https://example.com/about': '<html><body>About us</body></html>',
        }
    )

    result = CustomCareerPagesSource().fetch_jobs([SearchQuery(text='vision engineer germany')], context)

    assert result.raw_jobs == 1
    assert result.matched_jobs == 1
    assert len(result.discovered_jobs) == 1
    assert result.jobs[0].title == 'Vision Engineer'
    assert result.jobs[0].source == 'custom_career_pages'


def test_custom_career_pages_uses_sitemap_fallback() -> None:
    landing = '<html><body><p>No direct job links here.</p></body></html>'
    sitemap = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/perception-engineer</loc></url></urlset>'
    detail = '<html><head><title>Perception Engineer</title></head><body><h1>Perception Engineer</h1><p>Responsibilities include multimodal perception, robotics, and deployment. Apply now.</p></body></html>'
    context = FakeContext(
        {
            'https://example.com/careers': landing,
            'https://example.com/sitemap.xml': sitemap,
            'https://example.com/sitemap_index.xml': '',
            'https://example.com/jobs/perception-engineer': detail,
        }
    )

    result = CustomCareerPagesSource().fetch_jobs([SearchQuery(text='perception engineer')], context)

    assert result.raw_jobs == 1
    assert len(result.discovered_jobs) == 1
    assert result.jobs[0].title == 'Perception Engineer'


def test_extract_links_by_selector_reads_rendered_job_cards() -> None:
    html = '<html><body><a class="m-results__anchor" href="/de-de/unternehmen/karriere/stellenangebote/senior-key-account-manager-automotive-oem-wmd-3456">Job</a></body></html>'

    links = CustomCareerPagesSource._extract_links_by_selector(
        html,
        'https://www.kuka.com/de-de/unternehmen/karriere/stellenangebote',
        'www.kuka.com',
        'a.m-results__anchor',
    )

    assert links == ['https://www.kuka.com/de-de/unternehmen/karriere/stellenangebote/senior-key-account-manager-automotive-oem-wmd-3456']


def test_custom_career_pages_can_use_rendered_fallback() -> None:
    page_config = CustomCareerPageConfig(
        name='KUKA Careers',
        company='KUKA',
        url='https://www.kuka.com/de-de/unternehmen/karriere',
        include_url_patterns=['/stellenangebote/'],
        render_javascript=True,
        rendered_link_selector='a.m-results__anchor',
    )
    context = FakeContext(
        {
            'https://www.kuka.com/de-de/unternehmen/karriere': '<html><body><p>No job anchors in static HTML</p></body></html>',
            'https://www.kuka.com/de-de/unternehmen/karriere/stellenangebote/senior-key-account-manager-automotive-oem-wmd-3456': '<html><head><title>Senior Key Account Manager Automotive OEM (w/m/d)</title></head><body><h1>Senior Key Account Manager Automotive OEM (w/m/d)</h1><p>Responsibilities and apply details for a hybrid role in Augsburg.</p><p>Apply now</p></body></html>',
        },
        page_config=page_config,
    )

    result = RenderedSource([
        'https://www.kuka.com/de-de/unternehmen/karriere/stellenangebote/senior-key-account-manager-automotive-oem-wmd-3456'
    ]).fetch_jobs([SearchQuery(text='key account manager')], context)

    assert result.raw_jobs == 1
    assert result.discovered_jobs[0].source_url.endswith('senior-key-account-manager-automotive-oem-wmd-3456')
