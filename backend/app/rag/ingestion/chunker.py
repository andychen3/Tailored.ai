class Chunker:
    def __init__(self, window_seconds: int = 120, overlap_seconds: int = 15) -> None:
        self.window_seconds = window_seconds
        self.overlap_seconds = overlap_seconds

    def chunk_transcript(self, transcript: list[dict]) -> list[dict]:
        if not transcript:
            return []

        chunks = []
        current_chunk = []
        current_start = transcript[0]["start"]

        for entry in transcript:
            current_chunk.append(entry)
            elapsed = entry["start"] - current_start

            if elapsed >= self.window_seconds:
                chunk_text = " ".join(e["text"] for e in current_chunk)
                timestamp = self._format_timestamp(current_start)
                chunks.append(
                    {
                        "text": chunk_text,
                        "timestamp": timestamp,
                        "start_seconds": current_start,
                    }
                )

                # keep overlap: roll back entries within overlap window
                overlap_start = entry["start"] - self.overlap_seconds
                current_chunk = [
                    e for e in current_chunk if e["start"] >= overlap_start
                ]
                current_start = (
                    current_chunk[0]["start"] if current_chunk else entry["start"]
                )

        # flush the last chunk
        if current_chunk:
            chunk_text = " ".join(e["text"] for e in current_chunk)
            chunks.append(
                {
                    "text": chunk_text,
                    "timestamp": self._format_timestamp(current_start),
                    "start_seconds": int(current_start),
                }
            )

        return chunks

    def _format_timestamp(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"
