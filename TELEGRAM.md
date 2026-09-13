# AutoClip Telegram + GitHub Actions

AutoClip can be driven from a Telegram bot while the video-processing job runs on GitHub Actions. The GitHub runner performs Whisper transcription, local Ollama AI clip selection, caption rendering, and 9:16 Reel encoding. No paid AI API is required.

## Architecture

Telegram -> Azure Functions webhook -> GitHub Actions -> Ollama + faster-whisper + FFmpeg -> Telegram

The Azure gateway is in `azure_function/`. It is intentionally lightweight: Azure only receives Telegram webhooks and dispatches GitHub Actions. The AI/video processing stays on GitHub Actions.

## 1. GitHub repository secret

Add this Actions secret to the AutoClip repository:

- `TELEGRAM_BOT_TOKEN`: token from BotFather for the bot that receives the clips.

The workflow reads the Telegram chat ID from the workflow input and sends finished MP4s directly to that chat.

## 2. Azure Function App configuration

Create a Python Azure Function App and deploy the contents of `azure_function/`. Add these Application Settings:

- `TELEGRAM_BOT_TOKEN`: same BotFather token.
- `TELEGRAM_WEBHOOK_SECRET`: a long random secret used to authenticate Telegram webhook calls.
- `GITHUB_ACTIONS_TOKEN`: the fine-grained GitHub token with **Actions: Read and write** permission on `TTTT55/autoclip`.
- `GITHUB_REPO`: `TTTT55/autoclip`.
- `GITHUB_REF`: `main` after the feature branch is merged.
- `ALLOWED_CHAT_IDS`: `394533027` (your Telegram numeric chat ID).
- `MAX_CLIPS`: optional default, normally `5`.

The function exposes:

- `GET /api/health`
- `POST /api/telegram/webhook`

Azure Functions normally includes the `/api/` prefix in these URLs.

## 3. Set the Telegram webhook

After Azure gives you the Function App HTTPS hostname, configure Telegram using the same secret stored in Azure:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=https://YOUR-FUNCTION-APP.azurewebsites.net/api/telegram/webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

Then verify the webhook with Telegram's `getWebhookInfo` method.

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

**Important:** merge the `feat/ai-clipping` PR into `main` before using the Telegram gateway. The workflow must exist on the default branch for reliable `workflow_dispatch` use.

## 6. Local AI

Install Ollama, then pull a local model:

```bash
ollama pull qwen3:8b
```

Copy `.env.example` to `.env` and run the FastAPI app. Ollama's local API is used without an API key.

For lower-memory machines, use `qwen3:4b` or `qwen3:1.7b`.
