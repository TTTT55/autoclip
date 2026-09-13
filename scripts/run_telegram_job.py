import json
import os
import sys
import time
from pathlib import Path

import requests

from app.models import AIClipRequest
from engine.pipeline import get_job, start_job


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
JOB_ID = os.environ.get("AUTOCLIP_JOB_ID", "autoclip")


def telegram(method, **payload):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    response = requests.post(url, data=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def send_message(text):
    return telegram("sendMessage", chat_id=CHAT_ID, text=text)


def send_video(path, caption):
    path = Path(path)
    if path.stat().st_size > 49 * 1024 * 1024:
        # Telegram's Bot API currently caps multipart uploads at 50 MB. The
        # renderer normally keeps clips below this threshold; fail clearly if
        # a particular source still produces an oversized file.
        telegram("sendMessage", chat_id=CHAT_ID, text=f"⚠️ {caption}\nFile is larger than Telegram's 50 MB bot upload limit: {path.name}")
        return False
    with path.open("rb") as video:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "supports_streaming": "true",
            },
            files={"video": (path.name, video, "video/mp4")},
            timeout=300,
        )
        response.raise_for_status()
    return True


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_telegram_job.py VIDEO_URL [MAX_CLIPS]")

    url = sys.argv[1]
    max_clips = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    request = AIClipRequest(
        source="youtube",
        url=url,
        max_clips=max_clips,
        aspect_ratio="9:16",
        caption_style="word_pop",
        min_duration=20,
        max_duration=60,
    )

    job_id = start_job(request)
    send_message(f"🤖 AutoClip job started\nJob: {JOB_ID}\nFormat: 9:16 Reels\nAI: local Qwen3")

    last_stage = None
    while True:
        job = get_job(job_id)
        if not job:
            raise RuntimeError("AutoClip job disappeared")
        stage = job.get("stage")
        if stage != last_stage:
            print(json.dumps(job), flush=True)
            last_stage = stage
        if job["status"] == "complete":
            break
        if job["status"] == "error":
            raise RuntimeError(job.get("error", "Unknown AutoClip error"))
        time.sleep(5)

    clips = job.get("clips", [])
    if not clips:
        send_message("⚠️ AutoClip finished, but no suitable clips were found.")
        return

    send_message(f"✅ AutoClip finished — {len(clips)} clip(s) generated.")
    for index, clip in enumerate(clips, 1):
        caption = f"🎬 Clip {index}/{len(clips)} — {clip.get('title', 'AI clip')}\n⭐ {clip.get('score', 0)}/100\n{clip.get('hook', '')}"
        send_video(clip["file"], caption)


if __name__ == "__main__":
    main()
