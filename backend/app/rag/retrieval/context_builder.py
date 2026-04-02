def format_source_tag(*, title: str, timestamp: str, page_number: int | None) -> str:
    if title and timestamp:
        return f"{title} @ {timestamp}"
    if title and page_number:
        return f"{title} p.{page_number}"
    if title:
        return title
    if timestamp:
        return timestamp
    return "Source"


def build_source_url(*, source_type: str, video_id: str) -> str | None:
    if source_type == "youtube" and video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def build_context_and_sources(relevant_hits: list[dict]) -> tuple[str, list[dict]]:
    chunks: list[str] = []
    dedupe_keys: set[tuple[str, str, int | None]] = set()
    sources: list[dict] = []

    for hit in relevant_hits:
        chunk_text = hit["chunk_text"]
        title = hit["title"]
        timestamp = hit["timestamp"]
        video_id = hit["video_id"]
        source_type = hit["source_type"]
        page_number = hit["page_number"]

        source_tag = format_source_tag(
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
                "url": build_source_url(source_type=source_type, video_id=video_id),
            }
        )

    return "\n\n---\n\n".join(chunks), sources
