"""
Uchiro Clips — Telegram bot
Auto-cuts your own uploaded videos into highlight clips using real server-side
ffmpeg analysis (audio loudness + scene-cut detection), exports for
TikTok/YouTube/Square with no watermark, and can mix in music you upload.

Honest scope, on purpose:
- This bot only processes videos YOU send it. It does not download other
  people's TikTok/YouTube videos — that's a ToS/copyright issue regardless
  of the interface, so it's intentionally not built here.
- "Trend matching" (see trends.py) is a stub: real trend data requires a
  paid search API key that only you can provide, so it's left as a clearly
  marked extension point rather than faked.
"""

import os
import re
import json
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path

import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("uchiro-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
# Render sets RENDER_EXTERNAL_URL automatically; WEBHOOK_URL lets you override elsewhere.
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")

WORKDIR = Path(tempfile.gettempdir()) / "uchiro_sessions"
WORKDIR.mkdir(exist_ok=True)

PRESETS = {
    "tiktok": (1080, 1920),
    "youtube": (1920, 1080),
    "square": (1080, 1080),
}
LENGTH_OPTIONS = [("15s", 15), ("30s", 30), ("1 min", 60), ("5 min", 300)]
MAX_CLIPS = 8  # keep bounded so a free-tier server doesn't choke on huge videos

sessions = {}  # chat_id -> dict of in-progress state


# ---------------------------------------------------------------- ffmpeg utils

def run(cmd):
    log.info("RUN: %s", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError("Could not read this video (unsupported/corrupt file).")


def get_audio_energy(path, window_sec=0.5):
    """Decode audio to mono 16kHz PCM and compute RMS loudness per window."""
    sr = 16000
    cmd = ["ffmpeg", "-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le",
           "-ac", "1", "-ar", str(sr), "-v", "error", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if not proc.stdout:
        return []
    audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    win = max(1, int(sr * window_sec))
    energies = []
    for i in range(0, len(audio), win):
        chunk = audio[i:i + win]
        if len(chunk) == 0:
            break
        energies.append(float(np.sqrt(np.mean(chunk ** 2))))
    return energies


def get_scene_cuts(path, threshold=0.35):
    """Use ffmpeg's scene-change detector to find natural cut points."""
    cmd = ["ffmpeg", "-i", str(path), "-vf", f"select='gt(scene,{threshold})',showinfo",
           "-f", "null", "-v", "info", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    times = []
    for line in proc.stderr.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            times.append(float(m.group(1)))
    return times


def find_peaks(energies, window_sec, min_gap_sec, top_n):
    if not energies:
        return []
    arr = np.array(energies)
    if arr.max() - arr.min() < 1e-9:
        return []  # flat/no signal — don't fake a result
    mean, std = arr.mean(), arr.std()
    threshold = mean + std * 0.7
    candidates = []
    for i in range(1, len(arr) - 1):
        if arr[i] > threshold and arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1]:
            candidates.append((i * window_sec, float(arr[i])))
    candidates.sort(key=lambda c: -c[1])
    chosen = []
    for t, v in candidates:
        if all(abs(t - c[0]) > min_gap_sec for c in chosen):
            chosen.append((t, v))
        if len(chosen) >= top_n:
            break
    return sorted(chosen)


def build_clips(duration, energies, scene_cuts, length_sec, max_clips, window_sec):
    peaks = find_peaks(energies, window_sec, max(3, length_sec * 0.6), max_clips)
    clips = []
    for t, score in peaks:
        start = max(0.0, t - length_sec / 2)
        end = min(duration, start + length_sec)
        start = max(0.0, end - length_sec)
        near_cuts = [c for c in scene_cuts if start - 3 <= c <= start + 1]
        if near_cuts:
            start = max(near_cuts)
            end = min(duration, start + length_sec)
        clips.append({"start": start, "end": end, "score": score})
    if not clips:
        s = 0.0
        while s < duration and len(clips) < min(3, max_clips):
            clips.append({"start": s, "end": min(duration, s + length_sec), "score": 0.5})
            s += length_sec
    return clips[:max_clips]


def render_clip(video_path, clip, preset, out_path, music_path=None, text=None):
    w, h = PRESETS.get(preset, (1080, 1920))
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if text:
        safe = text.replace("\\", "").replace("'", "").replace(":", "")
        vf += (f",drawtext=text='{safe}':fontcolor=white:fontsize=48:"
               f"box=1:boxcolor=black@0.55:boxborderw=16:x=(w-text_w)/2:y=h*0.85")

    cmd = ["ffmpeg", "-y", "-ss", f"{clip['start']:.2f}", "-to", f"{clip['end']:.2f}",
           "-i", str(video_path)]

    if music_path:
        cmd += ["-i", str(music_path)]
        filter_complex = (
            f"[0:v]{vf}[v];"
            f"[0:a]volume=1.0[a0];[1:a]volume=0.6,aloop=loop=-1:size=2e9[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])


# ---------------------------------------------------------------- bot handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a video (your own footage) and I'll auto-cut it into highlight clips, "
        "tag them, and export ready for TikTok/YouTube/Square — no watermark.\n\n"
        "Optional: send a music file *before* the video and I'll mix it in.\n\n"
        "This bot only edits videos you upload — it can't fetch or download other "
        "people's TikTok/YouTube videos.",
        parse_mode="Markdown",
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tg_file = update.message.audio or update.message.voice or update.message.document
    if not tg_file:
        return
    file = await tg_file.get_file()
    session_dir = WORKDIR / str(chat_id)
    session_dir.mkdir(exist_ok=True)
    music_path = session_dir / "music.mp3"
    await file.download_to_drive(str(music_path))
    sessions.setdefault(chat_id, {})["music_path"] = music_path
    await update.message.reply_text("Got the track — I'll mix it into the next video you send.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tg_file = update.message.video or (
        update.message.document if update.message.document and
        (update.message.document.mime_type or "").startswith("video/") else None
    )
    if not tg_file:
        return

    await update.message.reply_text("Downloading and checking your video…")
    file = await tg_file.get_file()
    session_dir = WORKDIR / str(chat_id)
    session_dir.mkdir(exist_ok=True)
    video_path = session_dir / "input.mp4"
    await file.download_to_drive(str(video_path))

    try:
        duration = ffprobe_duration(video_path)
    except RuntimeError as e:
        await update.message.reply_text(f"Couldn't read that video: {e}")
        return

    prev = sessions.get(chat_id, {})
    sessions[chat_id] = {
        "video_path": video_path,
        "duration": duration,
        "music_path": prev.get("music_path"),
        "length": 30,
        "preset": "tiktok",
    }

    kb = [[InlineKeyboardButton(label, callback_data=f"len:{secs}") for label, secs in LENGTH_OPTIONS]]
    await update.message.reply_text(
        f"Loaded ({duration:.0f}s). Pick a clip length:",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def on_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    if chat_id not in sessions:
        await q.edit_message_text("Session expired — please send the video again.")
        return
    secs = int(q.data.split(":")[1])
    sessions[chat_id]["length"] = secs
    kb = [
        [InlineKeyboardButton("TikTok/Shorts 9:16", callback_data="preset:tiktok")],
        [InlineKeyboardButton("YouTube 16:9", callback_data="preset:youtube")],
        [InlineKeyboardButton("Square 1:1", callback_data="preset:square")],
    ]
    await q.edit_message_text(f"Length set to {secs}s. Now pick export format:",
                               reply_markup=InlineKeyboardMarkup(kb))


async def on_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    if chat_id not in sessions:
        await q.edit_message_text("Session expired — please send the video again.")
        return
    preset = q.data.split(":")[1]
    sessions[chat_id]["preset"] = preset
    await q.edit_message_text(f"Format: {preset}. Processing now — this can take a minute…")
    await process_and_send(chat_id, context)


async def process_and_send(chat_id, context: ContextTypes.DEFAULT_TYPE):
    s = sessions[chat_id]
    video_path, duration = s["video_path"], s["duration"]
    length_sec, preset, music_path = s["length"], s["preset"], s.get("music_path")
    window_sec = max(0.5, duration / 240)

    try:
        energies = get_audio_energy(video_path, window_sec)
        scene_cuts = get_scene_cuts(video_path)
    except Exception as e:
        await context.bot.send_message(chat_id, f"Analysis failed: {e}\nGenerating evenly-spaced clips instead.")
        energies, scene_cuts = [], []

    clips = build_clips(duration, energies, scene_cuts, length_sec, MAX_CLIPS, window_sec)
    mean_score = float(np.mean([c["score"] for c in clips])) if clips else 0.5
    session_dir = video_path.parent

    for i, clip in enumerate(clips):
        out_path = session_dir / f"clip_{i + 1}.mp4"
        tag = "🔥 Highlight" if clip["score"] > mean_score else "✨ Nice Moment"
        try:
            render_clip(video_path, clip, preset, out_path, music_path=music_path, text=tag)
            with open(out_path, "rb") as f:
                await context.bot.send_video(
                    chat_id, f,
                    caption=f"Clip {i + 1} — {tag} ({clip['end'] - clip['start']:.0f}s)"
                )
        except Exception as e:
            await context.bot.send_message(chat_id, f"Clip {i + 1} failed to render: {e}")

    await context.bot.send_message(chat_id, "Done! Send another video anytime.")
    shutil.rmtree(session_dir, ignore_errors=True)
    sessions.pop(chat_id, None)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(CallbackQueryHandler(on_length, pattern=r"^len:"))
    app.add_handler(CallbackQueryHandler(on_preset, pattern=r"^preset:"))

    if WEBHOOK_URL:
        log.info("Starting in webhook mode at %s", WEBHOOK_URL)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{BOT_TOKEN}",
        )
    else:
        log.info("No WEBHOOK_URL set — starting in polling mode (fine for local testing).")
        app.run_polling()


if __name__ == "__main__":
    main()
