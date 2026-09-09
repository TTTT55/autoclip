import os, subprocess, uuid
from .captions import write_ass, words_for_range

def render_clip(video, start, end, words, aspect_ratio="9:16", caption_style="word_pop"):
    os.makedirs("temp", exist_ok=True)
    stem=f"temp/{uuid.uuid4()}"
    ass=stem+".ass"; output=stem+".mp4"
    local_words=[{"start":max(0,w["start"]-start),"end":max(0,w["end"]-start),"text":w["text"]} for w in words_for_range(words,start,end)]
    write_ass(local_words,ass,caption_style)
    vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if aspect_ratio=="1:1": vf="scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    elif aspect_ratio=="16:9": vf="scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    vf += f",subtitles={ass}"
    subprocess.run(["ffmpeg","-y","-ss",str(start),"-to",str(end),"-i",video,"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-movflags","+faststart",output],check=True)
    return output
