import re
from dataclasses import dataclass


@dataclass(slots=True)
class RetrievalNormalizationResult:
    query: str
    applied: bool


_RETRIEVAL_SYNONYMS = (
    (
        re.compile(r"\bllms\b", re.IGNORECASE),
        "large language models",
    ),
    (
        re.compile(r"\bllm\b", re.IGNORECASE),
        "large language model",
    ),
)


def normalize_query(query: str) -> RetrievalNormalizationResult:
    normalized = query.strip()
    if not normalized:
        return RetrievalNormalizationResult(query="", applied=False)

    applied = False
    for pattern, replacement in _RETRIEVAL_SYNONYMS:
        updated = pattern.sub(replacement, normalized)
        if updated != normalized:
            normalized = updated
            applied = True

    normalized = re.sub(r"\s+", " ", normalized).strip()
    return RetrievalNormalizationResult(query=normalized, applied=applied)
