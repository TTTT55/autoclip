from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from engine.youtube import download_youtube
from engine.drive import download_drive
from engine.clipper import clip_video

app = FastAPI(title="AutoClip API")

# 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/clip")
def clip(source: str, url: str, start: str, end: str):
    if source == "youtube":
        video = download_youtube(url)
    else:
        video = download_drive(url)

    output = clip_video(video, start, end)
    return {"status": "success", "file": output}
