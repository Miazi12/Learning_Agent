"""
transcriber.py
--------------
লোকাল ভিডিও/অডিও ফাইল (FB থেকে সেভ করা, course app থেকে স্ক্রিন-রেকর্ড করা,
বা YouTube fallback audio) কে faster-whisper দিয়ে টেক্সটে রূপান্তর করে।
"""

import os

_model_cache = {}


def _get_model(model_size: str = "small"):
    if model_size not in _model_cache:
        from faster_whisper import WhisperModel
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def transcribe_file(file_path: str, model_size: str = "small", language: str | None = None) -> str:
    """
    যেকোনো ভিডিও/অডিও ফাইল (mp4, mp3, mkv, wav, m4a ইত্যাদি) টেক্সটে রূপান্তর করে।
    language=None দিলে auto-detect করবে (বাংলা/ইংরেজি দুটোই চলবে)।
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ফাইল পাওয়া যায়নি: {file_path}")

    model = _get_model(model_size)
    segments, info = model.transcribe(file_path, language=language, vad_filter=True)

    print(f"  → শনাক্ত হওয়া ভাষা: {info.language} (confidence: {info.language_probability:.2f})")

    full_text = []
    for seg in segments:
        full_text.append(seg.text.strip())

    return " ".join(full_text)
