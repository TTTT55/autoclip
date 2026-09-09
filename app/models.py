from pydantic import BaseModel, Field
from typing import Optional

class AIClipRequest(BaseModel):
    source: str = "youtube"
    url: str
    max_clips: int = Field(default=5, ge=1, le=20)
    aspect_ratio: str = "9:16"
    caption_style: str = "word_pop"
    min_duration: int = Field(default=20, ge=5, le=180)
    max_duration: int = Field(default=60, ge=10, le=300)
    language: Optional[str] = None

class ClipCandidate(BaseModel):
    start: float
    end: float
    score: int
    title: str
    hook: str
    reason: str
    transcript: str
    file: Optional[str] = None

class AIJob(BaseModel):
    id: str
    status: str
    progress: int = 0
    stage: str = "queued"
    error: Optional[str] = None
    clips: list[ClipCandidate] = []
