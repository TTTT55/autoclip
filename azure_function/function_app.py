import json
import os
import secrets
import uuid
from urllib.parse import urlparse

import azure.functions as func
import requests

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_ACTIONS_TOKEN"]
TELEGRAM_WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
GITHUB_REPO = os.getenv("GITHUB_REPO", "TTTT55/autoclip")
GITHUB_REF = os.getenv("GITHUB_REF", "main")
MAX_CLIPS = int(os.getenv("MAX_CLIPS", "5"))
ALLOWED_CHAT_IDS = {
    value.strip()
    for value in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if value.strip()
}


def telegram(method, **payload):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def reply(chat_id, text):
    telegram("sendMessage", chat_id=chat_id, text=text)


def looks_like_url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def parse_request(text):
    parts = text.strip().split()
    if parts and parts[0].startswith("/"):
        command = parts[0].split("@")[0].lower()
        if command in {"/start", "/help"}:
            return command, None, MAX_CLIPS
        if command == "/clip":
            args = parts[1:]
            if args and args[0].isdigit():
                count = max(1, min(20, int(args[0])))
                args = args[1:]
            else:
                count = MAX_CLIPS
            return command, args[0] if args else None, count
        return command, None, MAX_CLIPS
    return "clip", parts[0] if parts else None, MAX_CLIPS


def dispatch_workflow(video_url, chat_id, max_clips):
    job_id = uuid.uuid4().hex[:12]
    endpoint = (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        "/actions/workflows/ai-clip.yml/dispatches"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    payload = {
        "ref": GITHUB_REF,
        "inputs": {
            "video_url": video_url,
            "chat_id": str(chat_id),
            "max_clips": str(max_clips),
            "job_id": job_id,
        },
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"GitHub workflow dispatch failed ({response.status_code}): "
            f"{response.text[:500]}"
        )
    return job_id


@app.route(route="telegram/webhook", methods=["POST"])
def telegram_webhook(req: func.HttpRequest) -> func.HttpResponse:
    supplied_secret = req.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(supplied_secret, TELEGRAM_WEBHOOK_SECRET):
        return func.HttpResponse("Forbidden", status_code=403)

    try:
        update = req.get_json()
    except ValueError:
        return func.HttpResponse("Bad JSON", status_code=400)

    message = update.get("message") or update.get("edited_message")
    if not message:
        return func.HttpResponse(
            json.dumps({"ok": True}),
            status_code=200,
            mimetype="application/json",
        )

    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS:
        return func.HttpResponse(
            json.dumps({"ok": True}),
            status_code=200,
            mimetype="application/json",
        )

    text = message.get("text", "")
    command, url, max_clips = parse_request(text)

    if command in {"/start", "/help"}:
        reply(
            chat_id,
            "🎬 AutoClip\n\n"
            "Send a YouTube/video URL to generate AI-selected 9:16 Reels "
            "with captions.\n\n"
            "Optional: /clip 5 <URL>",
        )
    elif command == "/clip" and not url:
        reply(chat_id, "Usage: /clip 5 https://example.com/video")
    elif not url or not looks_like_url(url):
        reply(
            chat_id,
            "Please send a valid video URL. You can paste the URL directly "
            "or use /clip 5 <URL>.",
        )
    else:
        try:
            job_id = dispatch_workflow(url, chat_id, max_clips)
            reply(
                chat_id,
                f"🚀 AutoClip started\nJob: {job_id}\n"
                f"Format: 9:16 Instagram Reels\nClips: {max_clips}\n\n"
                "I'll send the finished clips here when GitHub Actions completes them.",
            )
        except Exception as exc:
            reply(chat_id, f"❌ Could not start AutoClip.\n\n{exc}")

    return func.HttpResponse(
        json.dumps({"ok": True}),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "ok", "service": "autoclip-telegram-azure"}),
        status_code=200,
        mimetype="application/json",
    )
