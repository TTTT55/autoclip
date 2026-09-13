"""AI clip selection using a local Ollama model.

No paid API key is required. Ollama exposes its local API on port 11434 by
 default; see .env.example for configuration.
"""

import json
import os
from typing import Any

import requests


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))


def _chat(prompt: str) -> dict[str, Any]:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional short-form video editor. Return only the requested JSON. Do not explain your reasoning.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0.15},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Ollama returned an empty response")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {content[:500]}") from exc


def select_clips(transcript, max_clips=5, min_duration=20, max_duration=60):
    words = transcript.get("words", [])
    if not words:
        raise RuntimeError("Transcript contains no timestamped words")

    # Keep the prompt bounded for long videos. The editor receives numbered
    # transcript words so it can choose precise boundaries without guessing time.
    max_words = int(os.getenv("AI_MAX_TRANSCRIPT_WORDS", "12000"))
    indexed_words = [
        {"i": i, "text": w["text"]}
        for i, w in enumerate(words[:max_words])
    ]

    prompt = f"""Find the {max_clips} strongest self-contained moments in this transcript.

Rules:
- Prefer hooks, surprising insights, stories, humor, emotion, useful advice,
  strong opinions, controversy, and clear payoffs.
- Avoid greetings, introductions, sponsor/ad sections, filler, incomplete thoughts,
  and clips that require missing context.
- Each clip must be {min_duration}-{max_duration} seconds based on the timestamps
  represented by the word indexes.
- Start and end at natural sentence/thought boundaries.
- Do not overlap clips unless absolutely necessary.
- Rank the best clips first.
- Use only the supplied word indexes. Never invent indexes.
- score must be an integer from 0 to 100.

Return exactly this JSON shape:
{{
  "clips": [
    {{
      "start_word": 0,
      "end_word": 100,
      "score": 92,
      "title": "Short compelling title",
      "hook": "One-sentence hook",
      "reason": "Why this moment works as a short"
    }}
  ]
}}

TRANSCRIPT WORDS:
{json.dumps(indexed_words, ensure_ascii=False)}
"""

    data = _chat(prompt)
    clips = []
    for raw in data.get("clips", []):
        try:
            start_index = int(raw["start_word"])
            end_index = int(raw["end_word"])
            score = max(0, min(100, int(raw.get("score", 0))))
        except (KeyError, TypeError, ValueError):
            continue

        start_index = max(0, min(len(words) - 1, start_index))
        end_index = max(start_index, min(len(words) - 1, end_index))
        start = words[start_index]["start"]
        end = words[end_index]["end"]
        duration = end - start
        if duration < min_duration or duration > max_duration:
            continue

        clips.append(
            {
                "start": start,
                "end": end,
                "score": score,
                "title": str(raw.get("title", "AI clip"))[:120],
                "hook": str(raw.get("hook", ""))[:300],
                "reason": str(raw.get("reason", ""))[:500],
                "transcript": " ".join(w["text"] for w in words[start_index : end_index + 1]),
            }
        )

    clips.sort(key=lambda c: c["score"], reverse=True)
    return clips[:max_clips]
