import uuid

from app.rag.ingestion.chunker import Chunker


PINECONE_BATCH_SIZE = 90


def build_youtube_records(
    *,
    user_id: str,
    source_id: str,
    video_id: str,
    video_title: str,
    transcript,
) -> list[dict]:
    chunks = Chunker().chunk_transcript(transcript)
    return [
        {
            "id": f"{source_id}:{index}",
            "chunk_text": chunk["text"],
            "user_id": user_id,
            "source_id": source_id,
            "source_type": "youtube",
            "video_id": video_id,
            "video_title": video_title,
            "timestamp": chunk["timestamp"],
        }
        for index, chunk in enumerate(chunks)
    ]


def build_file_records(
    *,
    user_id: str,
    file_path: str,
    filename: str,
    source_type: str,
    source_id: str,
) -> tuple[list[dict], str]:
    file_id = (
        f"{filename.rsplit('.', 1)[0].lower().replace(' ', '_')}"
        f"_{uuid.uuid4().hex[:8]}"
    )

    if source_type == "video_file":
        from app.rag.ingestion.video_file_ingester import VideoFileIngester

        transcript = VideoFileIngester().extract_transcript(file_path)
        chunks = Chunker().chunk_transcript(transcript)
        records = [
            {
                "id": f"{source_id}:{index}",
                "chunk_text": chunk["text"],
                "user_id": user_id,
                "source_id": source_id,
                "source_type": source_type,
                "file_id": file_id,
                "file_name": filename,
                "timestamp": chunk["timestamp"],
            }
            for index, chunk in enumerate(chunks)
        ]
        return records, file_id

    if source_type == "pdf":
        from app.rag.ingestion.pdf_ingester import PDFIngester
        from app.rag.ingestion.text_chunker import TextChunker

        pages = PDFIngester().extract_pages(file_path)
        chunker = TextChunker()
        records: list[dict] = []
        index = 0
        for page in pages:
            for chunk in chunker.chunk_text(page["text"]):
                records.append(
                    {
                        "id": f"{source_id}:{index}",
                        "chunk_text": chunk["text"],
                        "user_id": user_id,
                        "source_id": source_id,
                        "source_type": source_type,
                        "file_id": file_id,
                        "file_name": filename,
                        "timestamp": "",
                        "page_number": page["page"],
                    }
                )
                index += 1
        return records, file_id

    from app.rag.ingestion.text_chunker import TextChunker
    from app.rag.ingestion.text_file_ingester import TextFileIngester

    text = TextFileIngester().extract_text(file_path)
    chunks = TextChunker().chunk_text(text)
    records = [
        {
            "id": f"{source_id}:{index}",
            "chunk_text": chunk["text"],
            "user_id": user_id,
            "source_id": source_id,
            "source_type": source_type,
            "file_id": file_id,
            "file_name": filename,
            "timestamp": "",
        }
        for index, chunk in enumerate(chunks)
    ]
    return records, file_id
