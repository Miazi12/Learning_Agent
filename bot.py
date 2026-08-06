"""
bot.py
------
Learning Agent - Telegram Bot ভার্সন
"""

import os
import re
import logging
import tempfile
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from transcript_source import is_youtube_url, get_youtube_transcript, download_audio_for_whisper
from transcriber import transcribe_file
from summarizer import summarize_transcript

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")

MAX_FILE_SIZE_MB = 20

URL_PATTERN = re.compile(r"https?://\S+")


def _run_health_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")

        def log_message(self, format, *args):
            pass

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 স্বাগতম! আমি আপনার Learning Agent।\n\n"
        "আমাকে পাঠান:\n"
        "📺 YouTube link — সরাসরি প্রসেস করব\n"
        "🎬 ভিডিও/অডিও ফাইল (২০MB পর্যন্ত) — forward বা সরাসরি পাঠান\n\n"
        "আমি ফেরত দেব:\n"
        "• সংক্ষিপ্ত সারমর্ম\n"
        "• ধাপে-ধাপে ওয়ার্কফ্লো\n"
        "• সমস্যা ও সমাধান\n"
        "• মনে রাখার মূল পয়েন্ট\n\n"
        "শুরু করতে একটা লিংক বা ফাইল পাঠান!"
    )


async def _run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "একটা YouTube link পাঠান, অথবা ভিডিও/অডিও ফাইল পাঠান। "
            "সাহায্য দরকার হলে /start লিখুন।"
        )
        return

    url = match.group(0)

    if not is_youtube_url(url):
        await update.message.reply_text(
            "❌ এই লিংকটা সরাসরি সাপোর্টেড না (এখন শুধু YouTube link সাপোর্টেড)।\n\n"
            "বিকল্প: ভিডিওটা ডাউনলোড/স্ক্রিন-রেকর্ড করে সেই ফাইলটা (২০MB পর্যন্ত) "
            "সরাসরি আমাকে পাঠান — আমি সেটাও প্রসেস করতে পারি।"
        )
        return

    status_msg = await update.message.reply_text("🔍 YouTube caption খোঁজা হচ্ছে...")

    try:
        result = await _run_blocking(get_youtube_transcript, url)

        if result:
            transcript, title = result
        else:
            await status_msg.edit_text("🎧 caption নেই, audio ডাউনলোড করে transcribe করা হচ্ছে (একটু সময় লাগবে)...")
            audio_path = await _run_blocking(download_audio_for_whisper, url)
            transcript = await _run_blocking(transcribe_file, audio_path, WHISPER_MODEL)
            title = os.path.basename(audio_path)
            try:
                os.remove(audio_path)
            except OSError:
                pass

        await _summarize_and_reply(status_msg, update, transcript, title, url)

    except Exception as e:
        logger.exception("YouTube প্রসেসিং এ সমস্যা")
        await status_msg.edit_text(f"❌ কিছু একটা সমস্যা হয়েছে: {str(e)[:200]}")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    file_obj = msg.video or msg.audio or msg.voice or msg.document

    if not file_obj:
        return

    file_size_mb = (file_obj.file_size or 0) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        await msg.reply_text(
            f"❌ ফাইলটা {file_size_mb:.1f}MB — Telegram bot সর্বোচ্চ {MAX_FILE_SIZE_MB}MB "
            "পর্যন্ত ফাইল ডাউনলোড করতে পারে। ছোট অংশে ভাগ করে পাঠান, অথবা YouTube-এ "
            "আপলোড করে (unlisted) link পাঠান।"
        )
        return

    status_msg = await msg.reply_text("📥 ফাইল ডাউনলোড করা হচ্ছে...")

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_obj.file_name or f"{file_obj.file_id}.bin")

    try:
        tg_file = await file_obj.get_file()
        await tg_file.download_to_drive(local_path)

        await status_msg.edit_text("🎧 transcribe করা হচ্ছে (একটু সময় লাগতে পারে)...")
        transcript = await _run_blocking(transcribe_file, local_path, WHISPER_MODEL)
        title = file_obj.file_name or "ভিডিও"

        await _summarize_and_reply(status_msg, update, transcript, title, "লোকাল ফাইল")

    except Exception as e:
        logger.exception("ফাইল প্রসেসিং এ সমস্যা")
        await status_msg.edit_text(f"❌ কিছু একটা সমস্যা হয়েছে: {str(e)[:200]}")
    finally:
        try:
            os.remove(local_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


async def _summarize_and_reply(status_msg, update: Update, transcript: str, title: str, source: str) -> None:
    if not transcript or len(transcript.strip()) < 20:
        await status_msg.edit_text("❌ যথেষ্ট টেক্সট পাওয়া যায়নি, প্রসেস বাতিল করা হলো।")
        return

    await status_msg.edit_text(f"🧠 ট্রান্সক্রিপ্ট পাওয়া গেছে ({len(transcript)} অক্ষর)। Claude দিয়ে নোট বানানো হচ্ছে...")

    summary = await _run_blocking(summarize_transcript, transcript, title)

    await status_msg.delete()

    header = f"📚 *{title}*\n_সোর্স: {source}_\n\n"
    full_text = header + summary

    for i in range(0, len(full_text), 4000):
        await update.message.reply_text(full_text[i:i + 4000], parse_mode="Markdown")

    tmp_note = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp_note.write(f"# {title}\n\n**সোর্স:** {source}\n\n---\n\n{summary}")
    tmp_note.close()
    await update.message.reply_document(document=open(tmp_note.name, "rb"), filename=f"{title[:40]}.md")
    os.remove(tmp_note.name)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable সেট করা নেই।")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY environment variable সেট করা নেই।")

    threading.Thread(target=_run_health_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL,
        handle_media
    ))

    logger.info("Bot চালু হচ্ছে...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
