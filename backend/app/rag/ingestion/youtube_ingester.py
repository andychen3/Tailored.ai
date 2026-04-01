from urllib.parse import urlparse, parse_qs
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


class YouTubeIngester:
    def __init__(self) -> None:
        self.api = YouTubeTranscriptApi()

    def get_video_info(self, url: str) -> dict:
        opts = {"quiet": True, "skip_download": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "YouTube Video"),
                "video_id": info.get("id"),
            }

    def get_video_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.hostname == "youtu.be":
            return parsed.path[1:]
        return parse_qs(parsed.query).get("v", [None])[0]

    def fetch_transcript(self, url: str) -> tuple[str, list[dict]]:
        video_id = self.get_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        try:
            transcript_list = self.api.fetch(video_id)
            transcript = [
                {
                    "text": snippet.text,
                    "start": snippet.start,
                    "duration": snippet.duration,
                }
                for snippet in transcript_list
            ]
            return video_id, transcript

        except TranscriptsDisabled:
            raise ValueError(f"Transcripts are disabled for video: {video_id}")
        except NoTranscriptFound:
            raise ValueError(f"No transcript found for video: {video_id}")
