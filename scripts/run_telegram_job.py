import json
import os
import sys
import time
from pathlib import Path

# When this file is executed as `python scripts/run_telegram_job.py`, Python
# puts `scripts/` on sys.path rather than the repository root. Add the root so
# the application packages can be imported reliably in GitHub Actions and
# local CLI usage.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from app.models import AIClipRequest
from engine.pipeline import get_job, start_job


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
JOB_ID = os.environ.get("AUTOCLIP_JOB_ID", "autoclip")
TELEGRAM_UPLOAD_TIMEOUT = int(os.getenv("TELEGRAM_UPLOAD_TIMEOUT", "900"))
TELEGRAM_UPLOAD_RETRIES = max(1, int(os.getenv("TELEGRAM_UPLOAD_RETRIES", "3")))


def telegram(method, **payload):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    response = requests.post(url, data=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def send_message(text):
    return telegram("sendMessage", chat_id=CHAT_ID, text=text)


def send_video(path, caption):
    path = Path(path)
    size = path.stat().st_size
    if size > 49 * 1024 * 1024:
        send_message(
            f"⚠️ {caption}\n"
            f"File is larger than Telegram's 50 MB bot upload limit: {path.name}"
        )
        return False

    last_error = None
    for attempt in range(1, TELEGRAM_UPLOAD_RETRIES + 1):
        try:
            with path.open("rb") as video:
                response = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                    data={
                        "chat_id": CHAT_ID,
                        "caption": caption,
                        "supports_streaming": "true",
                    },
                    files={"video": (path.name, video, "video/mp4")},
                    timeout=(30, TELEGRAM_UPLOAD_TIMEOUT),
                )
                response.raise_for_status()
            return True
        except requests.RequestException as exc:
            last_error = exc
            print(
                f"Telegram upload attempt {attempt}/{TELEGRAM_UPLOAD_RETRIES} "
                f"failed for {path.name}: {exc}",
                flush=True,
            )
            if attempt < TELEGRAM_UPLOAD_RETRIES:
                time.sleep(min(30, 5 * attempt))

    send_message(
        f"⚠️ Could not send generated clip `{path.name}` to Telegram after "
        f"{TELEGRAM_UPLOAD_RETRIES} attempts. The clip is still available in "
        f"the GitHub Actions artifact.\nError: {last_error}"
    )
    return False


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
    sent = 0
    failed = 0
    for index, clip in enumerate(clips, 1):
        caption = (
            f"🎬 Clip {index}/{len(clips)} — {clip.get('title', 'AI clip')}\n"
            f"⭐ {clip.get('score', 0)}/100\n{clip.get('hook', '')}"
        )
        if send_video(clip["file"], caption):
            sent += 1
        else:
            failed += 1

    if failed:
        send_message(
            f"⚠️ AutoClip processing completed: {sent}/{len(clips)} clips sent to Telegram. "
            f"{failed} upload(s) failed; generated files remain in the GitHub Actions artifact."
        )
    else:
        send_message(f"✅ All {sent} generated clip(s) were sent successfully.")


if __name__ == "__main__":
    main()
