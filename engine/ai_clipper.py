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
            "options": {"temperature": 0.1},
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


def _fallback_clip(words, min_duration, max_duration):
    """Return a deterministic clip when the small local model selects nothing."""
    if not words:
        return None

    target = min(45.0, max_duration)
    target = max(float(min_duration), target)
    if words[-1]["end"] - words[0]["start"] < min_duration:
        return None

    # Prefer a window near the middle, then move it toward a natural boundary.
    center = (words[0]["start"] + words[-1]["end"]) / 2
    start_pos = min(
        range(len(words)),
        key=lambda i: abs(((words[i]["start"] + words[i]["end"]) / 2) - (center - target / 2)),
    )
    end_time = words[start_pos]["start"] + target
    end_pos = min(range(start_pos, len(words)), key=lambda i: abs(words[i]["end"] - end_time))

    if end_pos <= start_pos:
        end_pos = min(len(words) - 1, start_pos + 1)
    start = words[start_pos]["start"]
    end = words[end_pos]["end"]
    duration = end - start

    if duration < min_duration:
        end_pos = min(len(words) - 1, end_pos + 1)
        end = words[end_pos]["end"]
        duration = end - start
    if duration < min_duration or duration > max_duration:
        return None

    return {
        "start": start,
        "end": end,
        "score": 50,
        "title": "AI-selected highlight",
        "hook": "A highlight selected from the video's transcript.",
        "reason": "Fallback used because the local model did not return a valid duration-constrained clip.",
        "transcript": " ".join(w["text"] for w in words[start_pos : end_pos + 1]),
    }


def select_clips(transcript, max_clips=5, min_duration=20, max_duration=60):
    words = transcript.get("words", [])
    if not words:
        raise RuntimeError("Transcript contains no timestamped words")

    # Keep the prompt bounded for long videos. Crucially, include timestamps:
    # the model cannot satisfy duration constraints if it only sees word text.
    max_words = int(os.getenv("AI_MAX_TRANSCRIPT_WORDS", "12000"))
    indexed_words = [
        {
            "i": i,
            "s": round(float(w["start"]), 2),
            "e": round(float(w["end"]), 2),
            "text": w["text"],
        }
        for i, w in enumerate(words[:max_words])
    ]

    prompt = f"""Find up to {max_clips} strongest self-contained moments in this transcript.

Rules:
- Prefer hooks, surprising insights, stories, humor, emotion, useful advice,
  strong opinions, controversy, and clear payoffs.
- Avoid greetings, introductions, sponsor/ad sections, filler, incomplete thoughts,
  and clips that require missing context.
- Each clip MUST be {min_duration}-{max_duration} seconds. Use the supplied s/e
  timestamps to calculate the duration before returning an index pair.
- Start and end at natural sentence/thought boundaries.
- Do not overlap clips unless absolutely necessary.
- Rank the best clips first.
- Use only supplied word indexes. Never invent indexes.
- score must be an integer from 0 to 100.
- If fewer than {max_clips} good moments exist, return fewer rather than invalid clips.

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

TRANSCRIPT WORDS (i=index, s=start seconds, e=end seconds):
{json.dumps(indexed_words, ensure_ascii=False)}
"""

    data = _chat(prompt)
    clips = []
    seen_ranges = set()
    for raw in data.get("clips", []):
        try:
            start_index = int(raw["start_word"])
            end_index = int(raw["end_word"])
            score = max(0, min(100, int(raw.get("score", 0))))
        except (KeyError, TypeError, ValueError):
            continue

        start_index = max(0, min(len(words) - 1, start_index))
        end_index = max(start_index, min(len(words) - 1, end_index))
        start = float(words[start_index]["start"])
        end = float(words[end_index]["end"])
        duration = end - start
        if duration < min_duration or duration > max_duration:
            continue

        range_key = (start_index, end_index)
        if range_key in seen_ranges:
            continue
        seen_ranges.add(range_key)

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
    clips = clips[:max_clips]

    # Never silently return an empty result for a normal-length video. A small
    # local model can fail to satisfy strict index/duration constraints; use a
    # deterministic fallback so the rendering pipeline can still be exercised.
    if not clips:
        fallback = _fallback_clip(words, min_duration, max_duration)
        if fallback:
            clips = [fallback]

    return clips
