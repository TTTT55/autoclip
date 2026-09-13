import os
from faster_whisper import WhisperModel

_model = None

def get_model():
    global _model
    if _model is None:
        _model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device=os.getenv("WHISPER_DEVICE", "cpu"), compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    return _model

def transcribe(video_file, language=None):
    model = get_model()
    segments, info = model.transcribe(video_file, language=language, word_timestamps=True, vad_filter=True)
    words, text_segments = [], []
    for segment in segments:
        text_segments.append(segment.text.strip())
        for word in segment.words or []:
            words.append({"start": word.start, "end": word.end, "text": word.word.strip()})
    return {"language": info.language, "duration": info.duration, "text": " ".join(text_segments), "words": words}
