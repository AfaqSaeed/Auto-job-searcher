"""Optional embedding-based similarity scoring."""

from __future__ import annotations

from dataclasses import dataclass

from job_searcher.config import AppConfig
from job_searcher.schemas import JobListing, UserProfile
from job_searcher.utils.text import jaccard_similarity, tokenise, unique_preserve_order

_SENTENCE_TRANSFORMER_CLASS: object | None = None
_SENTENCE_TRANSFORMER_CHECKED = False


def _sentence_transformer_class() -> object | None:
    """Lazy-load the optional sentence-transformers dependency."""

    global _SENTENCE_TRANSFORMER_CLASS, _SENTENCE_TRANSFORMER_CHECKED
    if _SENTENCE_TRANSFORMER_CHECKED:
        return _SENTENCE_TRANSFORMER_CLASS
    _SENTENCE_TRANSFORMER_CHECKED = True
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:  # pragma: no cover - optional dependency
        _SENTENCE_TRANSFORMER_CLASS = None
    else:
        _SENTENCE_TRANSFORMER_CLASS = SentenceTransformer
    return _SENTENCE_TRANSFORMER_CLASS


@dataclass
class EmbeddingBackend:
    model_name: str
    model: object | None = None
    enabled: bool = True

    def load(self) -> None:
        if not self.enabled or self.model is not None:
            return
        sentence_transformer = _sentence_transformer_class()
        if sentence_transformer is None:
            return
        self.model = sentence_transformer(self.model_name)

    def similarity(self, left: str, right: str) -> float:
        if not self.enabled:
            return lexical_similarity(left, right)
        self.load()
        if self.model is None:
            return lexical_similarity(left, right)
        vectors = self.model.encode([left, right], normalize_embeddings=True)
        return float(vectors[0] @ vectors[1])


def lexical_similarity(left: str, right: str) -> float:
    left_tokens = set(tokenise(left))
    right_tokens = set(tokenise(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(overlap, jaccard_similarity(left, right))


def compute_profile_job_similarity(profile: UserProfile, job: JobListing, config: AppConfig) -> float:
    """Return a 0-100 similarity score using embeddings when available."""

    profile_text = " ".join(
        unique_preserve_order(
            [profile.summary or profile.llm_summary or ""]
            + [skill.name for skill in profile.skills]
            + profile.domain_strengths
            + profile.role_families
        )
    )
    job_text = " ".join(
        unique_preserve_order(
            [job.title, job.description, job.company]
            + job.required_skills
            + job.preferred_skills
            + job.domain_signals
        )
    )
    backend = EmbeddingBackend(config.embeddings.model_name, enabled=config.embeddings.enabled)
    similarity = backend.similarity(profile_text, job_text)
    return round(max(0.0, min(1.0, similarity)) * 100.0, 2)
