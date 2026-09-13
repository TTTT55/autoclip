from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from engine.youtube import download_youtube
from engine.drive import download_drive
from engine.clipper import clip_video
from app.models import AIClipRequest
from engine.pipeline import start_job, get_job
import os

app = FastAPI(title="AutoClip AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/clip")
def clip(source: str, url: str, start: str, end: str):
    video = download_youtube(url) if source == "youtube" else download_drive(url)
    return {"file": clip_video(video, start, end)}

@app.post("/ai/clip")
def ai_clip(request: AIClipRequest):
    return {"job_id": start_job(request)}

@app.get("/ai/clip/{job_id}")
def ai_clip_status(job_id: str):
    job=get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/download")
def download(file: str):
    if not os.path.isfile(file): raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file, filename=os.path.basename(file), media_type="video/mp4")
