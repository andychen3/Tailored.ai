import tempfile
import os

from faster_whisper import WhisperModel

# Load the model once at module level to avoid reloading on every call.
# "base" is ~140MB and fast on CPU. Upgrade to "small" or "medium" for
# better accuracy at the cost of speed.
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


class VideoFileIngester:
    def extract_transcript(self, file_path: str) -> list[dict]:
        """Extract and transcribe audio from a video file.

        Returns a list of dicts with keys 'text', 'start', 'duration' —
        the same shape as YouTubeIngester.fetch_transcript() so the existing
        Chunker.chunk_transcript() can be reused directly.
        """
        from moviepy.editor import VideoFileClip

        wav_path = None
        try:
            clip = VideoFileClip(file_path)
            audio = clip.audio
            if audio is None:
                raise ValueError("Video file has no audio track.")

            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                wav_path = tmp.name

            audio.write_audiofile(
                wav_path,
                fps=16000,
                nbytes=2,
                ffmpeg_params=["-ac", "1"],
            )
            clip.close()

            model = _get_model()
            segments, _ = model.transcribe(wav_path, beam_size=5)

            transcript = []
            for segment in segments:
                transcript.append({
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "duration": segment.end - segment.start,
                })

            return transcript
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
