import logging
import re
import uuid
from dataclasses import dataclass
from app.pinecone_client import index
from app.rag.ingestion.youtube_ingester import YouTubeIngester
from app.rag.ingestion.chunker import Chunker
from pinecone import SearchQuery
from typing import Any


PINECONE_BATCH_SIZE = 90  # Pinecone limit is 96; stay safely under
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievalNormalizationResult:
    query: str
    applied: bool


class RAGRetriever:
    MIN_SIMILARITY_SCORE = 0.3
    FALLBACK_MIN_SIMILARITY_SCORE = 0.22
    MIN_KEYWORD_LENGTH = 2
    _STOPWORDS = frozenset({
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

    def __init__(self):
        self.ingester = YouTubeIngester()
        self.chunker = Chunker()

    def normalize_query(self, query: str) -> RetrievalNormalizationResult:
        normalized = query.strip()
        if not normalized:
            return RetrievalNormalizationResult(query="", applied=False)

        applied = False
        for pattern, replacement in self._RETRIEVAL_SYNONYMS:
            updated = pattern.sub(replacement, normalized)
            if updated != normalized:
                normalized = updated
                applied = True

        normalized = re.sub(r"\s+", " ", normalized).strip()
        return RetrievalNormalizationResult(query=normalized, applied=applied)

    def ingest_youtube_url(
        self,
        user_id: str,
        url: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str]:
        video_info = self.ingester.get_video_info(url)
        video_title = video_info["title"]
        video_id, transcript = self.ingester.fetch_transcript(url)
        chunks = self.chunker.chunk_transcript(transcript)
        source_id = source_id or uuid.uuid4().hex

        records = [
            {
                "id": f"{source_id}:{i}",
                "chunk_text": chunk["text"],
                "user_id": user_id,
                "source_id": source_id,
                "source_type": "youtube",
                "video_id": video_id,
                "video_title": video_title,
                "timestamp": chunk["timestamp"],
            }
            for i, chunk in enumerate(chunks)
        ]

        for i in range(0, len(records), PINECONE_BATCH_SIZE):
            index.upsert_records(
                namespace="__default__",
                records=records[i : i + PINECONE_BATCH_SIZE],
            )
        return len(records), video_title, source_id

    def ingest_file(
        self,
        user_id: str,
        file_path: str,
        filename: str,
        source_type: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str, str]:
        """Ingest an uploaded file.

        Returns (chunk_count, file_id, filename, source_id).
        """
        source_id = source_id or uuid.uuid4().hex
        file_id = (
            f"{filename.rsplit('.', 1)[0].lower().replace(' ', '_')}"
            f"_{uuid.uuid4().hex[:8]}"
        )

        if source_type == "video_file":
            from app.rag.ingestion.video_file_ingester import VideoFileIngester
            transcript = VideoFileIngester().extract_transcript(file_path)
            chunks = self.chunker.chunk_transcript(transcript)
            records = [
                {
                    "id": f"{source_id}:{i}",
                    "chunk_text": chunk["text"],
                    "user_id": user_id,
                    "source_id": source_id,
                    "source_type": source_type,
                    "file_id": file_id,
                    "file_name": filename,
                    "timestamp": chunk["timestamp"],
                }
                for i, chunk in enumerate(chunks)
            ]
        elif source_type == "pdf":
            from app.rag.ingestion.pdf_ingester import PDFIngester
            from app.rag.ingestion.text_chunker import TextChunker
            pages = PDFIngester().extract_pages(file_path)
            chunker = TextChunker()
            records = []
            idx = 0
            for page in pages:
                page_chunks = chunker.chunk_text(page["text"])
                for chunk in page_chunks:
                    records.append({
                        "id": f"{source_id}:{idx}",
                        "chunk_text": chunk["text"],
                        "user_id": user_id,
                        "source_id": source_id,
                        "source_type": source_type,
                        "file_id": file_id,
                        "file_name": filename,
                        "timestamp": "",
                        "page_number": page["page"],
                    })
                    idx += 1
        else:
            from app.rag.ingestion.text_file_ingester import TextFileIngester
            from app.rag.ingestion.text_chunker import TextChunker
            text = TextFileIngester().extract_text(file_path)
            chunks = TextChunker().chunk_text(text)
            records = [
                {
                    "id": f"{source_id}:{i}",
                    "chunk_text": chunk["text"],
                    "user_id": user_id,
                    "source_id": source_id,
                    "source_type": source_type,
                    "file_id": file_id,
                    "file_name": filename,
                    "timestamp": "",
                }
                for i, chunk in enumerate(chunks)
            ]

        for i in range(0, len(records), PINECONE_BATCH_SIZE):
            index.upsert_records(
                namespace="__default__",
                records=records[i : i + PINECONE_BATCH_SIZE],
            )
        return len(records), file_id, filename, source_id

    def query(
        self, user_id: str, question: str, top_k: int = 12
    ) -> tuple[str, list[dict], bool]:
        normalization = self.normalize_query(question)
        retrieval_query = normalization.query or question.strip()
        hits = self._search_hits(
            user_id=user_id, question=retrieval_query, top_k=top_k
        )
        ranked_hits = self._rank_hits(hits, question=retrieval_query)
        relevant_hits = self._select_relevant_hits(
            ranked_hits=ranked_hits,
            normalized_query_applied=normalization.applied,
        )
        top_score = (
            ranked_hits[0]["similarity_score"]
            if ranked_hits
            else 0.0
        )
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

        context, sources = self._build_context_and_sources(
            relevant_hits
        )
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
        results = index.search(
            namespace="__default__",
            query=SearchQuery(
                inputs={"text": question},
                top_k=top_k,
                filter={"user_id": {"$eq": user_id}},
            ),
            fields=[
                "chunk_text",
                "video_title",
                "timestamp",
                "user_id",
                "video_id",
                "source_type",
                "file_name",
                "file_id",
                "page_number",
            ],
        )
        return self._extract_hits(results)

    def _rank_hits(
        self,
        hits: list[Any],
        *,
        question: str,
    ) -> list[dict]:
        query_keywords = self._extract_keywords(question)
        ranked_hits: list[dict] = []

        for hit in hits:
            fields = getattr(hit, "fields", {}) or {}
            score = getattr(hit, "_score", 0.0) or 0.0
            normalized_hit = self._normalize_hit(fields)
            normalized_hit["similarity_score"] = score
            chunk_keywords = self._extract_keywords(
                normalized_hit["chunk_text"]
            )
            overlap_terms = query_keywords.intersection(chunk_keywords)
            normalized_hit["keyword_overlap_count"] = len(
                overlap_terms
            )
            ranked_hits.append(normalized_hit)

        return ranked_hits

    def _normalize_hit(self, fields: dict) -> dict:
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

    def _build_context_and_sources(
        self,
        relevant_hits: list[dict],
    ) -> tuple[str, list[dict]]:
        chunks = []
        dedupe_keys = set()
        sources = []

        for hit in relevant_hits:
            chunk_text = hit["chunk_text"]
            title = hit["title"]
            timestamp = hit["timestamp"]
            video_id = hit["video_id"]
            source_type = hit["source_type"]
            page_number = hit["page_number"]

            source_tag = self._format_source_tag(
                title=title,
                timestamp=timestamp,
                page_number=page_number,
            )
            if chunk_text:
                chunks.append(f"[{source_tag}]\n{chunk_text}")

            source_key = (title, timestamp, page_number)
            if source_key in dedupe_keys:
                continue

            dedupe_keys.add(source_key)
            sources.append(
                {
                    "title": title,
                    "timestamp": timestamp,
                    "video_id": video_id,
                    "page_number": page_number,
                    "url": self._build_source_url(
                        source_type=source_type,
                        video_id=video_id,
                    ),
                }
            )

        context = "\n\n---\n\n".join(chunks)
        return context, sources

    def _format_source_tag(
        self,
        *,
        title: str,
        timestamp: str,
        page_number: int | None,
    ) -> str:
        if title and timestamp:
            return f"{title} @ {timestamp}"
        if title and page_number:
            return f"{title} p.{page_number}"
        if title:
            return title
        if timestamp:
            return timestamp
        return "Source"

    def _build_source_url(
        self,
        *,
        source_type: str,
        video_id: str,
    ) -> str | None:
        if source_type == "youtube" and video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return None

    def _extract_hits(self, results: Any) -> list[Any]:
        matches = getattr(results, "matches", None)
        if matches is not None:
            return list(matches)

        search_result = getattr(results, "result", None)
        hits = (
            getattr(search_result, "hits", None) if search_result else None
        )
        if hits is not None:
            return list(hits)

        return []

    def _normalize_token(self, token: str) -> str:
        token = token.lower()
        if len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token

    def _extract_keywords(self, text: str) -> set[str]:
        raw_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        keywords = {
            self._normalize_token(t)
            for t in raw_tokens
            if len(t) >= self.MIN_KEYWORD_LENGTH
            and t not in self._STOPWORDS
        }
        return keywords

    def _select_relevant_hits(
        self,
        ranked_hits: list[dict],
        *,
        normalized_query_applied: bool = False,
        max_hits: int = 3,
    ) -> list[dict]:
        if not ranked_hits:
            return []

        score_filtered = [
            h for h in ranked_hits
            if h.get("similarity_score", 0.0)
            >= self.MIN_SIMILARITY_SCORE
        ]

        if not score_filtered:
            if not normalized_query_applied:
                return []

            score_filtered = [
                h for h in ranked_hits
                if h.get("similarity_score", 0.0) >= self.FALLBACK_MIN_SIMILARITY_SCORE
                and h.get("keyword_overlap_count", 0) > 0
            ]

            if not score_filtered:
                return []

        max_overlap = max(
            h["keyword_overlap_count"] for h in score_filtered
        )

        for h in score_filtered:
            kw_norm = (
                h["keyword_overlap_count"] / max_overlap
                if max_overlap > 0
                else 0.0
            )
            h["combined_score"] = (
                0.7 * h["similarity_score"] + 0.3 * kw_norm
            )

        score_filtered.sort(
            key=lambda h: h["combined_score"], reverse=True
        )
        return score_filtered[:max_hits]
