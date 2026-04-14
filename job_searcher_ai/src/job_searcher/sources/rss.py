"""RSS job source connector."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from job_searcher.parsing.normalization import extract_domain_signals, extract_language_requirements, extract_skill_mentions, infer_work_mode, normalize_job_listing
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


class RSSSource(BaseJobSource):
    name = "rss"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.rss_feeds:
            result.notes.append("no RSS feeds were configured")
            return result

        for feed_url in context.config.sources.rss_feeds:
            xml_text = context.get_text(feed_url)
            if not xml_text:
                continue
            root = ET.fromstring(xml_text)
            items = root.findall('.//item')
            result.raw_jobs += len(items)
            for item in items:
                title = (item.findtext('title') or 'Unknown title').strip()
                description = (item.findtext('description') or '').strip()
                link = (item.findtext('link') or feed_url).strip()
                job = normalize_job_listing(
                    JobListing(
                        id=link,
                        source='rss',
                        source_url=link,
                        title=title,
                        company='RSS Import',
                        location=None,
                        work_mode=infer_work_mode(description),
                        description=description,
                        required_skills=extract_skill_mentions(description),
                        preferred_skills=[],
                        responsibilities=[],
                        minimum_qualifications=[],
                        domain_signals=extract_domain_signals(description),
                        application_url=link,
                        date_posted=item.findtext('pubDate'),
                        language_requirements=extract_language_requirements(description),
                        raw_payload={'feed_url': feed_url},
                    )
                )
                self.apply_query_filter(result, job, queries)

        result.diagnostics = context.take_diagnostics()
        return result
