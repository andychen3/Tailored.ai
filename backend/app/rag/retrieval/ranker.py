import re
from typing import Any


STOPWORDS = frozenset({
    "the", "be", "to", "of", "and", "in", "that", "have", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say",
    "her", "she", "or", "an", "will", "my", "one", "all",
    "would", "there", "their", "what", "so", "up", "out", "if",
    "about", "who", "get", "which", "go", "me", "when", "make",
    "can", "like", "no", "just", "him", "know", "take",
    "come", "could", "than", "look", "want", "give", "use",
    "find", "here", "thing", "many", "well", "also", "tell",
})


def normalize_hit(fields: dict) -> dict:
    chunk_text = fields.get("chunk_text", "") or ""
    source_type = fields.get("source_type", "youtube") or "youtube"
    timestamp = fields.get("timestamp", "") or ""
    page_number = fields.get("page_number") or None

    if source_type == "youtube":
        title = fields.get("video_title", "") or ""
        video_id = fields.get("video_id", "") or ""
        file_name = ""
    else:
        title = fields.get("file_name", "") or ""
        video_id = ""
        file_name = title

    return {
        "chunk_text": chunk_text,
        "title": title,
        "timestamp": timestamp,
        "video_id": video_id,
        "file_name": file_name,
        "source_type": source_type,
        "page_number": page_number,
    }


def normalize_token(token: str) -> str:
    token = token.lower()
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def extract_keywords(text: str, *, min_keyword_length: int) -> set[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {
        normalize_token(token)
        for token in raw_tokens
        if len(token) >= min_keyword_length and token not in STOPWORDS
    }


def rank_hits(
    hits: list[Any],
    *,
    question: str,
    min_keyword_length: int,
) -> list[dict]:
    query_keywords = extract_keywords(question, min_keyword_length=min_keyword_length)
    ranked_hits: list[dict] = []

    for hit in hits:
        fields = getattr(hit, "fields", {}) or {}
        score = getattr(hit, "_score", 0.0) or 0.0
        normalized = normalize_hit(fields)
        normalized["similarity_score"] = score
        chunk_keywords = extract_keywords(
            normalized["chunk_text"],
            min_keyword_length=min_keyword_length,
        )
        normalized["keyword_overlap_count"] = len(query_keywords.intersection(chunk_keywords))
        ranked_hits.append(normalized)

    return ranked_hits


def select_relevant_hits(
    ranked_hits: list[dict],
    *,
    normalized_query_applied: bool,
    min_similarity_score: float,
    fallback_min_similarity_score: float,
    max_hits: int = 3,
) -> list[dict]:
    if not ranked_hits:
        return []

    score_filtered = [
        hit for hit in ranked_hits
        if hit.get("similarity_score", 0.0) >= min_similarity_score
    ]

    if not score_filtered:
        if not normalized_query_applied:
            return []

        score_filtered = [
            hit for hit in ranked_hits
            if hit.get("similarity_score", 0.0) >= fallback_min_similarity_score
            and hit.get("keyword_overlap_count", 0) > 0
        ]
        if not score_filtered:
            return []

    max_overlap = max(hit["keyword_overlap_count"] for hit in score_filtered)
    for hit in score_filtered:
        kw_norm = hit["keyword_overlap_count"] / max_overlap if max_overlap > 0 else 0.0
        hit["combined_score"] = 0.7 * hit["similarity_score"] + 0.3 * kw_norm

    score_filtered.sort(key=lambda hit: hit["combined_score"], reverse=True)
    return score_filtered[:max_hits]
