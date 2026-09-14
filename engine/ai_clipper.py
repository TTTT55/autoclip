"""AI clip selection using a local Ollama model.

The selector builds sentence-aligned candidate windows across the whole video,
then asks Ollama to rank those candidates. This avoids position bias toward the
opening and prevents clips from ending in the middle of a spoken sentence.
"""

import hashlib
import json
import os
import random
import re
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
                "num_predict": 512,
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


def _sentence_ranges(words):
    """Group Whisper words into sentence-like ranges using punctuation and pauses."""
    ranges = []
    start = 0
    for i, word in enumerate(words):
        text = str(word.get("text", ""))
        next_start = float(words[i + 1]["start"]) if i + 1 < len(words) else None
        end = float(word["end"])
        punctuation = bool(re.search(r"[.!?][\"')\]]*$", text))
        long_pause = next_start is not None and next_start - end >= 0.9
        if punctuation or long_pause or i == len(words) - 1:
            ranges.append({
                "start_word": start,
                "end_word": i,
                "start": float(words[start]["start"]),
                "end": end,
                "text": " ".join(w["text"] for w in words[start : i + 1]),
            })
            start = i + 1
    return ranges


def _build_candidates(words, min_duration, max_duration):
    """Build sentence-aligned candidate windows distributed across the video."""
    sentences = _sentence_ranges(words)
    if not sentences:
        return []

    total = float(words[-1]["end"]) - float(words[0]["start"])
    if total < min_duration:
        return []

    target = min(42.0, float(max_duration))
    target = max(float(min_duration), target)

    candidates = []
    seen = set()
    for start_sentence in range(len(sentences)):
        start_time = sentences[start_sentence]["start"]
        # Ignore starts that cannot possibly make a minimum-length clip.
        if float(words[-1]["end"]) - start_time < min_duration:
            break

        best_end = None
        for end_sentence in range(start_sentence, len(sentences)):
            duration = sentences[end_sentence]["end"] - start_time
            if duration < min_duration:
                continue
            if duration > max_duration:
                break
            # Prefer a natural end closest to the target duration.
            distance = abs(duration - target)
            if best_end is None or distance < best_end[0]:
                best_end = (distance, end_sentence)

        if best_end is None:
            continue
        end_sentence = best_end[1]
        start_index = sentences[start_sentence]["start_word"]
        end_index = sentences[end_sentence]["end_word"]
        key = (start_index, end_index)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "id": len(candidates) + 1,
            "start_word": start_index,
            "end_word": end_index,
            "start": round(float(words[start_index]["start"]), 2),
            "end": round(float(words[end_index]["end"]), 2),
            "text": " ".join(w["text"] for w in words[start_index : end_index + 1]),
        })

    # Keep a diverse set of candidates rather than feeding every overlapping
    # sentence window to the small local model. Prefer evenly distributed starts.
    if len(candidates) > 14:
        positions = [round(i * (len(candidates) - 1) / 13) for i in range(14)]
        candidates = [candidates[i] for i in sorted(set(positions))]

    # Candidate 1 must not always mean "the opening". Shuffle the candidate
    # presentation order deterministically so Qwen cannot learn a positional bias.
    seed = int(hashlib.sha256(" ".join(w["text"] for w in words[:500]).encode("utf-8", "ignore")).hexdigest()[:8], 16)
    random.Random(seed).shuffle(candidates)
    for i, candidate in enumerate(candidates, 1):
        candidate["id"] = i

    return candidates


def _fallback_clip(words, min_duration, max_duration):
    """Return a sentence-aligned middle highlight when AI selection fails."""
    candidates = _build_candidates(words, min_duration, max_duration)
    if not candidates:
        return None
    candidate = min(candidates, key=lambda c: abs((c["start"] + c["end"]) / 2 - (words[0]["start"] + words[-1]["end"]) / 2))
    return {
        "start": candidate["start"],
        "end": candidate["end"],
        "score": 50,
        "title": "Highlight",
        "hook": "A highlight selected from the video's transcript.",
        "reason": "Fallback used because the local AI selector was unavailable or timed out.",
        "transcript": candidate["text"],
    }


def select_clips(transcript, max_clips=5, min_duration=20, max_duration=60):
    words = transcript.get("words", [])
    if not words:
        raise RuntimeError("Transcript contains no timestamped words")

    candidates = _build_candidates(words, min_duration, max_duration)
    if not candidates:
        return []

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

Important:
- The candidates are presented in RANDOMIZED order. Candidate ID/order has no relationship to quality or position in the video.
- Do NOT choose a candidate merely because it appears first in this list.
- Evaluate the actual spoken content.
- Prefer a strong standalone hook, useful or surprising information, story, humor,
  emotion, strong opinion, controversy, or a clear payoff.
- Avoid greetings, introductions, "in this video" setup, sponsor/ad sections,
  filler, repetition, and incomplete thoughts.
- Prefer candidates that make sense without context from earlier in the video.
- Candidates already begin and end at sentence/thought boundaries.
- Rank the strongest candidates first.
- Only use supplied candidate IDs.
- Return fewer than {max_clips} only if there genuinely are not enough strong moments.

Return exactly:
{{"clips":[{{"id":1,"score":92,"title":"Short compelling title","hook":"One-sentence hook","reason":"Why this works as a short"}}]}}

CANDIDATES:
{json.dumps(candidate_payload, ensure_ascii=False)}
"""

    try:
        data = _chat(prompt)
    except (requests.RequestException, RuntimeError, ValueError, TypeError):
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

        # A small opening penalty prevents the common failure mode where the
        # first candidate wins simply because it contains the video's intro.
        adjusted_score = score
        if candidate["start"] < 30.0 and score < 90:
            adjusted_score -= 12
        clips.append({
            "start": candidate["start"],
            "end": candidate["end"],
            "score": max(0, adjusted_score),
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
