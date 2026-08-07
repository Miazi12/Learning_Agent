"""
transcript_source.py
---------------------
YouTube link থেকে transcript বের করার চেষ্টা করে (caption থাকলে সরাসরি নেয়,
না থাকলে audio ডাউনলোড করে whisper দিয়ে transcribe করার জন্য পাঠায়)।
"""

import re
import os
import shutil
import tempfile
from urllib.parse import urlparse, parse_qs

_SECRET_COOKIES = "/etc/secrets/cookies.txt"
COOKIES_PATH = "/tmp/cookies.txt"

if os.path.exists(_SECRET_COOKIES) and not os.path.exists(COOKIES_PATH):
    shutil.copyfile(_SECRET_COOKIES, COOKIES_PATH)


def extract_video_id(url: str) -> str | None:
    """YouTube URL থেকে video ID বের করে"""
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")
    if parsed.hostname and "youtube.com" in parsed.hostname:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
    return None


def is_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


def get_youtube_transcript(url: str, languages=("bn", "en")) -> tuple[str, str] | None:
    """
    প্রথমে YouTube-এর নিজস্ব caption/subtitle টানার চেষ্টা করে।
    সফল হলে (transcript_text, title) রিটার্ন করে, না হলে None।
    """
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

    video_id = extract_video_id(url)
    if not video_id:
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(languages)
        except NoTranscriptFound:
            transcript = next(iter(transcript_list))

        entries = transcript.fetch()
        text = " ".join(e["text"] for e in entries)
        title = get_video_title(url) or video_id
        return text, title
    except (TranscriptsDisabled, NoTranscriptFound, Exception):
        return None


def get_video_title(url: str) -> str | None:
    """yt-dlp দিয়ে শুধু metadata (title) বের করে, ডাউনলোড না করে"""
    try:
        import yt_dlp
        opts = {"quiet": True, "skip_download": True}
        if os.path.exists(COOKIES_PATH):
            opts["cookiefile"] = COOKIES_PATH
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title")
    except Exception:
        return None


def download_audio_for_whisper(url: str, out_dir: str | None = None) -> str:
    """
    Caption না থাকলে fallback: yt-dlp দিয়ে শুধু audio ডাউনলোড করে,
    whisper transcription-এর জন্য ফাইল পাথ রিটার্ন করে।
    """
    import yt_dlp

    out_dir = out_dir or tempfile.mkdtemp()
    out_template = os.path.join(out_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
    }
    if os.path.exists(COOKIES_PATH):
        ydl_opts["cookiefile"] = COOKIES_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info["id"]
        return os.path.join(out_dir, f"{video_id}.mp3")
