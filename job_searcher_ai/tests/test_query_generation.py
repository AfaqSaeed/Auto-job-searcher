from pathlib import Path

from job_searcher.config import load_config
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.queries.generator import generate_search_queries


def test_generate_queries_includes_adjacent_roles_and_respects_limit() -> None:
    config = load_config(Path("config/settings.yaml"), project_root=Path.cwd())
    profile = extract_profile(read_profile_document(Path("data/profile_master.md")))

    queries = generate_search_queries(profile, config)
    texts = [query.text.lower() for query in queries]

    assert len(queries) <= config.search.query_limit
    assert any("computer vision engineer" in text for text in texts)
    assert any("perception engineer" in text for text in texts)
    assert len(texts) == len(set(texts))
