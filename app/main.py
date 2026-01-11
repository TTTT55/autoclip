from fastapi import FastAPI
from engine.youtube import download_youtube
from engine.drive import download_drive
from engine.clipper import clip_video

app = FastAPI(title="AutoClip API")

@app.post("/clip")
def clip(source: str, url: str, start: str, end: str):
    if source == "youtube":
        video = download_youtube(url)
    else:
        video = download_drive(url)

    output = clip_video(video, start, end)
    return {"status": "success", "file": output}
