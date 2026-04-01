from app.pinecone_client import index
from app.rag.ingestion.youtube_ingester import YouTubeIngester
from app.rag.ingestion.chunker import Chunker
from pinecone import SearchQuery
from typing import Any
import re
import uuid


PINECONE_BATCH_SIZE = 90  # Pinecone limit is 96; stay safely under


class RAGRetriever:
    MIN_KEYWORD_OVERLAP = 2

    def __init__(self):
        self.ingester = YouTubeIngester()
        self.chunker = Chunker()

    def ingest_youtube_url(self, user_id: str, url: str) -> tuple[int, str]:
        video_info = self.ingester.get_video_info(url)
        video_title = video_info["title"]
        video_id, transcript = self.ingester.fetch_transcript(url)
        chunks = self.chunker.chunk_transcript(transcript)

        records = [
            {
                "id": f"{user_id}_{video_id}_{i}",
                "chunk_text": chunk["text"],
                "user_id": user_id,
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
        return len(records), video_title

    def ingest_file(
        self,
        user_id: str,
        file_path: str,
        filename: str,
        source_type: str,
    ) -> tuple[int, str, str]:
        """Ingest an uploaded file.

        Returns (chunk_count, file_id, filename).
        """
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
                    "id": f"{user_id}_{file_id}_{i}",
                    "chunk_text": chunk["text"],
                    "user_id": user_id,
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
                        "id": f"{user_id}_{file_id}_{idx}",
                        "chunk_text": chunk["text"],
                        "user_id": user_id,
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
                    "id": f"{user_id}_{file_id}_{i}",
                    "chunk_text": chunk["text"],
                    "user_id": user_id,
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
        return len(records), file_id, filename

    def query(
        self, user_id: str, question: str, top_k: int = 12
    ) -> tuple[str, list[dict], bool]:
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

        hits = self._extract_hits(results)
        query_keywords = self._extract_keywords(question)
        ranked_hits: list[dict] = []

        for hit in hits:
            fields = getattr(hit, "fields", {}) or {}
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

            chunk_keywords = self._extract_keywords(chunk_text)
            overlap_terms = query_keywords.intersection(chunk_keywords)

            ranked_hits.append(
                {
                    "chunk_text": chunk_text,
                    "title": title,
                    "timestamp": timestamp,
                    "video_id": video_id,
                    "file_name": file_name,
                    "source_type": source_type,
                    "page_number": page_number,
                    "keyword_overlap_count": len(overlap_terms),
                }
            )

        fallback_hits = [h for h in ranked_hits if h["chunk_text"]][:3]
        relevant_hits = self._select_relevant_hits(ranked_hits)
        if not relevant_hits:
            if not fallback_hits:
                return "", [], False
            relevant_hits = fallback_hits

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

            source_tag = "Source"
            if title and timestamp:
                source_tag = f"{title} @ {timestamp}"
            elif title and page_number:
                source_tag = f"{title} p.{page_number}"
            elif title:
                source_tag = title
            elif timestamp:
                source_tag = timestamp
            if chunk_text:
                chunks.append(f"[{source_tag}]\n{chunk_text}")

            source_key = (title, timestamp, page_number)
            if source_key not in dedupe_keys:
                dedupe_keys.add(source_key)
                if source_type == "youtube" and video_id:
                    url = (
                        f"https://www.youtube.com/watch?v={video_id}"
                    )
                else:
                    url = None
                sources.append(
                    {
                        "title": title,
                        "timestamp": timestamp,
                        "video_id": video_id,
                        "page_number": page_number,
                        "url": url,
                    }
                )

        context = "\n\n---\n\n".join(chunks)
        return context, sources, True

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
            self._normalize_token(t) for t in raw_tokens if len(t) >= 5
        }
        return keywords

    def _select_relevant_hits(
        self, ranked_hits: list[dict], max_hits: int = 3
    ) -> list[dict]:
        if not ranked_hits:
            return []

        ranked_hits.sort(
            key=lambda h: h["keyword_overlap_count"], reverse=True
        )
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
