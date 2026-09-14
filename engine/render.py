import math
import os
import subprocess
import uuid

from .captions import write_ass, words_for_range
from .reframe import find_reframe_points


def _video_size(video):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)


def _crop_x_expression(points, scaled_width, crop_width):
    """Build a piecewise-linear FFmpeg crop-x expression from tracking points."""
    if not points:
        return str(max(0, (scaled_width - crop_width) // 2))

    positions = []
    max_x = max(0, scaled_width - crop_width)
    for t, center in points:
        x = int(round(_clamp(center, 0.0, 1.0) * scaled_width - crop_width / 2))
        x = max(0, min(max_x, x))
        positions.append((max(0.0, float(t)), x))

    if len(positions) == 1:
        return str(positions[0][1])

    # FFmpeg expressions use escaped commas inside if()/between-style functions.
    expr = str(positions[-1][1])
    for i in range(len(positions) - 2, -1, -1):
        t0, x0 = positions[i]
        t1, x1 = positions[i + 1]
        if t1 <= t0:
            expr = str(x0)
            continue
        slope = (x1 - x0) / (t1 - t0)
        segment = f"({x0}+({slope:.6f})*(t-{t0:.3f}))"
        expr = f"if(lt(t\\,{t1:.3f})\\,{segment}\\,{expr})"
    return expr


def _clamp(value, low, high):
    return max(low, min(high, value))


def render_clip(video, start, end, words, aspect_ratio="9:16", caption_style="word_pop", workdir="temp"):
    os.makedirs(workdir, exist_ok=True)
    stem = os.path.join(workdir, str(uuid.uuid4()))
    ass = stem + ".ass"
    output = stem + ".mp4"
    local_words = [
        {"start": max(0, w["start"] - start), "end": max(0, w["end"] - start), "text": w["text"]}
        for w in words_for_range(words, start, end)
    ]
    write_ass(local_words, ass, caption_style)

    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if aspect_ratio == "9:16" and os.getenv("AUTO_REFRAME", "true").lower() in {"1", "true", "yes", "on"}:
        try:
            source_width, source_height = _video_size(video)
            if source_width > source_height:
                scaled_width = int(math.ceil((source_width * 1920 / source_height) / 2) * 2)
                points = find_reframe_points(video, start, end, sample_interval=1.0)
                x_expr = _crop_x_expression(points, scaled_width, 1080)
                vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:{x_expr}:0"
        except Exception as exc:
            # Never make rendering fail because optional intelligent reframing
            # could not analyze a frame; revert to the reliable center crop.
            print(f"[reframe] falling back to center crop: {exc}")

    if aspect_ratio == "1:1":
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    elif aspect_ratio == "16:9":
        vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    vf += f",subtitles={ass}"

    duration = max(0.01, float(end) - float(start))
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(start), "-i", video, "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-maxrate", os.getenv("VIDEO_MAXRATE", "4.5M"),
            "-bufsize", os.getenv("VIDEO_BUFSIZE", "9M"),
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output,
        ],
        check=True,
    )
    return output
