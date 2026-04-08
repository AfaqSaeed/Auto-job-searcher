"""URL and robots helpers."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests


def join_url(base: str, href: str | None) -> str:
    """Join relative links safely."""

    return urljoin(base, href or "")


def domain_for_url(url: str) -> str:
    """Return the domain portion of a URL."""

    return urlparse(url).netloc


@lru_cache(maxsize=128)
def _load_robots(robots_url: str, user_agent: str, timeout: int) -> RobotFileParser | None:
    parser = RobotFileParser()
    try:
        response = requests.get(robots_url, timeout=timeout, headers={"User-Agent": user_agent})
        if response.status_code >= 400:
            return None
        parser.parse(response.text.splitlines())
        return parser
    except requests.RequestException:
        return None


def is_allowed_by_robots(url: str, user_agent: str, timeout: int = 10) -> bool:
    """Best-effort robots.txt check. Fail open if robots cannot be loaded."""

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = _load_robots(robots_url, user_agent, timeout)
    if parser is None:
        return True
    return parser.can_fetch(user_agent, url)
