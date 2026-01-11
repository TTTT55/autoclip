import subprocess, uuid

def clip_video(input_file, start, end):
    output = f"temp/{uuid.uuid4()}.mp4"
    subprocess.run([
        "ffmpeg", "-ss", start, "-to", end,
        "-i", input_file, "-c", "copy", output
    ])
    return output
