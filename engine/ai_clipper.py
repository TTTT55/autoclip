"""AI clip selection using a local Ollama model.

The selector intentionally sends a small set of candidate windows to Ollama
instead of the entire word-level transcript. This keeps CPU inference practical
on GitHub-hosted runners while still letting the model choose the best moment.
"""

import json
import os
from typing import Any

import requests


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


def _chat(prompt: str) -> dict[str, Any]:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional short-form video editor. Return only valid JSON. Do not explain your reasoning.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096,
                "num_predict": 256,
            },
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
    """Return a deterministic clip when the local model cannot select one."""
    if not words:
        return None

    total_duration = float(words[-1]["end"]) - float(words[0]["start"])
    if total_duration < min_duration:
        return None

    target = min(45.0, float(max_duration))
    target = max(float(min_duration), target)

    # Start around the middle, but clamp so the complete window fits.
    start_time = max(float(words[0]["start"]),
                     min((float(words[-1]["end"]) - target),
                         (float(words[0]["start"]) + float(words[-1]["end"]) - target) / 2))
    start_pos = min(range(len(words)), key=lambda i: abs(float(words[i]["start"]) - start_time))
    end_time = float(words[start_pos]["start"]) + target
    end_pos = min(range(start_pos, len(words)), key=lambda i: abs(float(words[i]["end"]) - end_time))

    start = float(words[start_pos]["start"])
    end = float(words[end_pos]["end"])
    if end - start < min_duration:
        for i in range(end_pos + 1, len(words)):
            if float(words[i]["end"]) - start >= min_duration:
                end_pos = i
                end = float(words[i]["end"])
                break

    duration = end - start
    if duration < min_duration or duration > max_duration:
        return None

    return {
        "start": start,
        "end": end,
        "score": 50,
        "title": "Highlight",
        "hook": "A highlight selected from the video's transcript.",
        "reason": "Fallback used because the local AI selector was unavailable or timed out.",
        "transcript": " ".join(w["text"] for w in words[start_pos : end_pos + 1]),
    }


def _build_candidates(words, min_duration, max_duration):
    """Build a small set of overlapping 20-60s candidate windows."""
    if not words:
        return []

    total = float(words[-1]["end"]) - float(words[0]["start"])
    target = min(45.0, float(max_duration))
    target = max(float(min_duration), target)
    if total < min_duration:
        return []

    # For short videos, use the whole useful range. For longer videos, sample
    # roughly every 30 seconds with overlap so interesting moments aren't missed.
    if total <= target:
        starts = [0.0]
    else:
        step = 30.0
        max_start = total - target
        starts = []
        pos = 0.0
        while pos <= max_start + 0.01:
            starts.append(pos)
            pos += step
        if starts[-1] < max_start - 5:
            starts.append(max_start)

    candidates = []
    seen = set()
    for candidate_id, relative_start in enumerate(starts[:12], 1):
        absolute_start = float(words[0]["start"]) + relative_start
        absolute_end = absolute_start + target
        start_index = min(range(len(words)), key=lambda i: abs(float(words[i]["start"]) - absolute_start))
        end_index = min(
            range(start_index, len(words)),
            key=lambda i: abs(float(words[i]["end"]) - absolute_end),
        )
        start = float(words[start_index]["start"])
        end = float(words[end_index]["end"])
        if end - start < min_duration or end - start > max_duration:
            continue
        key = (start_index, end_index)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "id": candidate_id,
            "start_word": start_index,
            "end_word": end_index,
            "start": round(start, 2),
            "end": round(end, 2),
            "text": " ".join(w["text"] for w in words[start_index : end_index + 1]),
        })

    return candidates


def select_clips(transcript, max_clips=5, min_duration=20, max_duration=60):
    words = transcript.get("words", [])
    if not words:
        raise RuntimeError("Transcript contains no timestamped words")

    candidates = _build_candidates(words, min_duration, max_duration)
    if not candidates:
        return []

    # The old implementation sent every timestamped word to Qwen. On a CPU-only
    # GitHub runner that can create a very large prompt and make a 1.7B model take
    # many minutes. Rank a handful of bounded candidate windows instead.
    candidate_payload = [
        {
            "id": c["id"],
            "start": c["start"],
            "end": c["end"],
            "text": c["text"],
        }
        for c in candidates
    ]

    prompt = f"""Choose up to {max_clips} best short-form video clips from these candidate windows.

Rules:
- Each candidate is already {min_duration}-{max_duration} seconds long.
- Prefer hooks, surprising insights, stories, humor, emotion, useful advice,
  strong opinions, controversy, and clear payoffs.
- Avoid greetings, introductions, ads, filler, and incomplete thoughts.
- Prefer candidates that work without extra context.
- Rank the strongest candidates first.
- Only use candidate IDs that are supplied.
- Return fewer than {max_clips} only if necessary.

Return exactly:
{{"clips":[{{"id":1,"score":92,"title":"Short compelling title","hook":"One-sentence hook","reason":"Why this works as a short"}}]}}

CANDIDATES:
{json.dumps(candidate_payload, ensure_ascii=False)}
"""

    try:
        data = _chat(prompt)
    except requests.RequestException:
        fallback = _fallback_clip(words, min_duration, max_duration)
        return [fallback] if fallback else []
    except (RuntimeError, ValueError, TypeError):
        fallback = _fallback_clip(words, min_duration, max_duration)
        return [fallback] if fallback else []

    by_id = {c["id"]: c for c in candidates}
    clips = []
    seen_ids = set()
    for raw in data.get("clips", []):
        try:
            candidate_id = int(raw["id"])
            score = max(0, min(100, int(raw.get("score", 0))))
        except (KeyError, TypeError, ValueError):
            continue
        candidate = by_id.get(candidate_id)
        if not candidate or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        clips.append({
            "start": candidate["start"],
            "end": candidate["end"],
            "score": score,
            "title": str(raw.get("title", "AI clip"))[:120],
            "hook": str(raw.get("hook", ""))[:300],
            "reason": str(raw.get("reason", ""))[:500],
            "transcript": candidate["text"],
        })

    clips.sort(key=lambda c: c["score"], reverse=True)
    clips = clips[:max_clips]

    if not clips:
        fallback = _fallback_clip(words, min_duration, max_duration)
        if fallback:
            clips = [fallback]

    return clips
