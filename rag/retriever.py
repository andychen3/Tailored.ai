from pinecone_client import index
from rag.ingestion.youtube_ingester import YouTubeIngester
from rag.ingestion.chunker import Chunker
from pinecone import SearchQuery
from typing import Any
import re


class RAGRetriever:
    MIN_KEYWORD_OVERLAP = 2

    def __init__(self):
        self.ingester = YouTubeIngester()
        self.chunker = Chunker()

    def ingest_youtube_url(self, user_id: str, url: str, video_title: str) -> int:
        video_id, transcript = self.ingester.fetch_transcript(url)
        chunks = self.chunker.chunk_transcript(transcript)

        records = [
            {
                "id": f"{user_id}_{video_id}_{i}",
                "chunk_text": chunk["text"],
                "user_id": user_id,
                "video_id": video_id,
                "video_title": video_title,
                "timestamp": chunk["timestamp"],
            }
            for i, chunk in enumerate(chunks)
        ]

        index.upsert_records(namespace="__default__", records=records)
        return len(records)  # return chunk count for UI feedback

    def query(
        self, user_id: str, question: str, top_k: int = 5
    ) -> tuple[str, list[dict], bool]:
        results = index.search(
            namespace="__default__",
            query=SearchQuery(
                inputs={"text": question},
                top_k=top_k,
                filter={"user_id": {"$eq": user_id}},
            ),
            fields=["chunk_text", "video_title", "timestamp", "user_id"],
        )

        hits = self._extract_hits(results)
        query_keywords = self._extract_keywords(question)
        ranked_hits: list[dict] = []

        for hit in hits:
            fields = getattr(hit, "fields", {}) or {}
            chunk_text = fields.get("chunk_text", "") or ""
            video_title = fields.get("video_title", "") or ""
            timestamp = fields.get("timestamp", "") or ""
            chunk_keywords = self._extract_keywords(chunk_text)
            overlap_terms = query_keywords.intersection(chunk_keywords)

            ranked_hits.append(
                {
                    "chunk_text": chunk_text,
                    "video_title": video_title,
                    "timestamp": timestamp,
                    "keyword_overlap_count": len(overlap_terms),
                }
            )

        relevant_hits = self._select_relevant_hits(ranked_hits)
        if not relevant_hits:
            return "", [], False

        chunks = []
        dedupe_keys = set()
        sources = []
        for hit in relevant_hits:
            chunk_text = hit["chunk_text"]
            video_title = hit["video_title"]
            timestamp = hit["timestamp"]

            source_tag = "Source"
            if video_title and timestamp:
                source_tag = f"{video_title} @ {timestamp}"
            elif video_title:
                source_tag = video_title
            elif timestamp:
                source_tag = timestamp
            if chunk_text:
                chunks.append(f"[{source_tag}]\n{chunk_text}")

            source_key = (video_title, timestamp)
            if source_key not in dedupe_keys:
                dedupe_keys.add(source_key)
                sources.append(
                    {
                        "title": video_title,
                        "timestamp": timestamp,
                    }
                )

        context = "\n\n---\n\n".join(chunks)
        return context, sources, True

    def _extract_hits(self, results: Any) -> list[Any]:
        matches = getattr(results, "matches", None)
        if matches is not None:
            return list(matches)

        search_result = getattr(results, "result", None)
        hits = getattr(search_result, "hits", None) if search_result else None
        if hits is not None:
            return list(hits)

        return []

    def _normalize_token(self, token: str) -> str:
        token = token.lower()
        if len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token

    def _extract_keywords(self, text: str) -> set[str]:
        # Lightweight keyword extraction without maintaining a stopword list.
        # Keeping only longer tokens reduces noise like "what", "tell", "about".
        raw_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        keywords = {self._normalize_token(t) for t in raw_tokens if len(t) >= 5}
        return keywords

    def _select_relevant_hits(self, ranked_hits: list[dict], max_hits: int = 3) -> list[dict]:
        if not ranked_hits:
            return []

        ranked_hits.sort(key=lambda h: h["keyword_overlap_count"], reverse=True)
        top_overlap = ranked_hits[0]["keyword_overlap_count"]
        if top_overlap < self.MIN_KEYWORD_OVERLAP:
            return []

        # Keep only hits with strong lexical overlap.
        filtered = [
            h
            for h in ranked_hits
            if h["keyword_overlap_count"] >= self.MIN_KEYWORD_OVERLAP
        ]
        return filtered[:max_hits]
