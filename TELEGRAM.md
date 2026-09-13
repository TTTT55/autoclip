# AutoClip Telegram + GitHub Actions

AutoClip can be driven from a Telegram bot while the video-processing job runs on GitHub Actions. The GitHub runner performs Whisper transcription, local Ollama AI clip selection, caption rendering, and 9:16 Reel encoding. No paid AI API is required.

## Architecture

Telegram -> Heroku webhook -> GitHub Actions -> Ollama + faster-whisper + FFmpeg -> Telegram

The Telegram gateway is in `telegram_bot/`. It is intentionally lightweight so the Heroku app does not need the AI dependencies.

## 1. GitHub repository secrets

Add this Actions secret to the AutoClip repository:

- `TELEGRAM_BOT_TOKEN`: token from BotFather for the bot that receives the clips.

The workflow reads the Telegram chat ID from the workflow input and sends finished MP4s directly to that chat.

## 2. Heroku config vars

Deploy the contents of `telegram_bot/` as the root of a small Heroku app. The app needs:

- `TELEGRAM_BOT_TOKEN`: same BotFather token.
- `TELEGRAM_WEBHOOK_SECRET`: a long random secret used to authenticate Telegram webhook calls.
- `GITHUB_ACTIONS_TOKEN`: a fine-grained GitHub token with **Actions: Read and write** permission on `TTTT55/autoclip`.
- `GITHUB_REPO`: `TTTT55/autoclip`.
- `GITHUB_REF`: `main` after the feature branch is merged.
- `ALLOWED_CHAT_IDS`: your Telegram numeric chat ID. This keeps strangers from using your bot.
- `MAX_CLIPS`: optional default, normally `5`.

The Heroku process is defined by `telegram_bot/Procfile`.

### Deploying the subdirectory with Heroku CLI

From a clone of this repository:

```bash
git subtree push --prefix telegram_bot heroku main
```

The subtree becomes the root of the Heroku app, so Heroku sees its `requirements.txt` and `Procfile` directly.

## 3. Set the Telegram webhook

After Heroku gives you an HTTPS app URL, call Telegram's `setWebhook` method with the same secret configured in Heroku:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=https://YOUR-HEROKU-APP.herokuapp.com/telegram/webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

## 4. Use the bot

Paste a supported video URL directly:

```text
https://www.youtube.com/watch?v=...
```

Or specify the number of clips:

```text
/clip 5 https://www.youtube.com/watch?v=...
```

Every remote job is rendered as **1080x1920 (9:16)** with automatic captions.

## 5. GitHub Actions

The workflow is `.github/workflows/ai-clip.yml`. It supports `workflow_dispatch`, so it can also be started manually from GitHub's Actions UI.

The cloud runner uses `qwen3:1.7b` and Whisper `base` to keep CPU processing practical. Local development can use larger models by changing `OLLAMA_MODEL` and `WHISPER_MODEL` in `.env`.

The workflow caches the Ollama and Whisper model files between runs and uploads generated MP4s as a short-lived artifact as a fallback.

## 6. Local AI

Install Ollama, then pull a local model:

```bash
ollama pull qwen3:8b
```

Copy `.env.example` to `.env` and run the FastAPI app. Ollama's local API is used without an API key.

For lower-memory machines, use `qwen3:4b` or `qwen3:1.7b`.
