import os
import shutil
import threading
import traceback
import uuid

from .youtube import download_youtube
from .drive import download_drive
from .transcription import transcribe
from .ai_clipper import select_clips
from .render import render_clip

JOBS = {}


def start_job(request):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "clips": [],
    }
    threading.Thread(target=run_job, args=(job_id, request), daemon=True).start()
    return job_id


def run_job(job_id, request):
    workdir = os.path.join("temp", job_id)
    try:
        os.makedirs(workdir, exist_ok=True)

        def setp(progress, stage):
            JOBS[job_id].update(progress=progress, stage=stage, status="processing")

        setp(5, "downloading")
        if request.source == "youtube":
            video = download_youtube(request.url, workdir)
        else:
            video = download_drive(request.url, workdir)

        setp(25, "transcribing")
        transcript = transcribe(video, request.language)

        setp(50, "finding best moments")
        clips = select_clips(
            transcript,
            request.max_clips,
            request.min_duration,
            request.max_duration,
        )
        JOBS[job_id]["clips"] = clips

        total = max(1, len(clips))
        for i, clip in enumerate(clips):
            clip["file"] = render_clip(
                video,
                clip["start"],
                clip["end"],
                transcript["words"],
                request.aspect_ratio,
                request.caption_style,
                workdir,
            )
            JOBS[job_id]["progress"] = 50 + int((i + 1) / total * 45)
            JOBS[job_id]["stage"] = f"rendering clip {i + 1}/{total}"

        JOBS[job_id].update(progress=100, stage="complete", status="complete")
    except Exception as exc:
        JOBS[job_id].update(
            status="error",
            stage="failed",
            error=f"{exc}\n{traceback.format_exc()}",
        )


def get_job(job_id):
    return JOBS.get(job_id)
