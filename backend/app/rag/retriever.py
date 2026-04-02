import logging
from typing import Any

from app.rag.ingestion.ingest_service import IngestService
from app.rag.retrieval.context_builder import (
    build_context_and_sources,
    build_source_url,
    format_source_tag,
)
from app.rag.retrieval.query_normalizer import (
    RetrievalNormalizationResult,
    normalize_query,
)
from app.rag.retrieval.ranker import (
    extract_keywords,
    normalize_hit,
    normalize_token,
    rank_hits,
    select_relevant_hits,
)
from app.rag.retrieval.search import extract_hits, search_hits

logger = logging.getLogger(__name__)


class RAGRetriever:
    MIN_SIMILARITY_SCORE = 0.3
    FALLBACK_MIN_SIMILARITY_SCORE = 0.22
    MIN_KEYWORD_LENGTH = 2

    def __init__(self):
        self.ingest_service = IngestService()
        self.ingester = self.ingest_service.youtube_ingester

    def normalize_query(self, query: str) -> RetrievalNormalizationResult:
        return normalize_query(query)

    def ingest_youtube_url(
        self,
        user_id: str,
        url: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str]:
        return self.ingest_service.ingest_youtube_url(
            user_id=user_id,
            url=url,
            source_id=source_id,
        )

    def ingest_file(
        self,
        user_id: str,
        file_path: str,
        filename: str,
        source_type: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str, str]:
        return self.ingest_service.ingest_file(
            user_id=user_id,
            file_path=file_path,
            filename=filename,
            source_type=source_type,
            source_id=source_id,
        )

    def query(
        self, user_id: str, question: str, top_k: int = 12
    ) -> tuple[str, list[dict], bool]:
        normalization = self.normalize_query(question)
        retrieval_query = normalization.query or question.strip()
        hits = self._search_hits(
            user_id=user_id,
            question=retrieval_query,
            top_k=top_k,
        )
        ranked_hits = self._rank_hits(hits, question=retrieval_query)
        relevant_hits = self._select_relevant_hits(
            ranked_hits=ranked_hits,
            normalized_query_applied=normalization.applied,
        )
        top_score = ranked_hits[0]["similarity_score"] if ranked_hits else 0.0
        if not relevant_hits:
            if not ranked_hits:
                rejection_reason = "no_hits"
            elif normalization.applied:
                rejection_reason = "below_fallback_threshold"
            else:
                rejection_reason = "below_similarity_threshold"
            logger.debug(
                "RAG query rejected as no-context",
                extra={
                    "user_id": user_id,
                    "question": question,
                    "retrieval_query": retrieval_query,
                    "query_normalized": normalization.applied,
                    "hit_count": len(hits),
                    "top_score": top_score,
                    "selected_hit_count": 0,
                    "rejection_reason": rejection_reason,
                },
            )
            return "", [], False

        context, sources = self._build_context_and_sources(relevant_hits)
        logger.debug(
            "RAG query completed",
            extra={
                "user_id": user_id,
                "question": question,
                "retrieval_query": retrieval_query,
                "query_normalized": normalization.applied,
                "hit_count": len(hits),
                "top_score": top_score,
                "selected_hit_count": len(relevant_hits),
                "fallback_used": normalization.applied and all(
                    hit.get("similarity_score", 0.0) < self.MIN_SIMILARITY_SCORE
                    for hit in relevant_hits
                ),
            },
        )
        return context, sources, True

    def _search_hits(
        self,
        *,
        user_id: str,
        question: str,
        top_k: int,
    ) -> list[Any]:
        return search_hits(user_id=user_id, question=question, top_k=top_k)

    def _rank_hits(
        self,
        hits: list[Any],
        *,
        question: str,
    ) -> list[dict]:
        return rank_hits(
            hits,
            question=question,
            min_keyword_length=self.MIN_KEYWORD_LENGTH,
        )

    def _normalize_hit(self, fields: dict) -> dict:
        return normalize_hit(fields)

    def _build_context_and_sources(
        self,
        relevant_hits: list[dict],
    ) -> tuple[str, list[dict]]:
        return build_context_and_sources(relevant_hits)

    def _format_source_tag(
        self,
        *,
        title: str,
        timestamp: str,
        page_number: int | None,
    ) -> str:
        return format_source_tag(
            title=title,
            timestamp=timestamp,
            page_number=page_number,
        )

    def _build_source_url(
        self,
        *,
        source_type: str,
        video_id: str,
    ) -> str | None:
        return build_source_url(source_type=source_type, video_id=video_id)

    def _extract_hits(self, results: Any) -> list[Any]:
        return extract_hits(results)

    def _normalize_token(self, token: str) -> str:
        return normalize_token(token)

    def _extract_keywords(self, text: str) -> set[str]:
        return extract_keywords(text, min_keyword_length=self.MIN_KEYWORD_LENGTH)

    def _select_relevant_hits(
        self,
        ranked_hits: list[dict],
        *,
        normalized_query_applied: bool = False,
        max_hits: int = 3,
    ) -> list[dict]:
        return select_relevant_hits(
            ranked_hits,
            normalized_query_applied=normalized_query_applied,
            min_similarity_score=self.MIN_SIMILARITY_SCORE,
            fallback_min_similarity_score=self.FALLBACK_MIN_SIMILARITY_SCORE,
            max_hits=max_hits,
        )
