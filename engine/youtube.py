import os
import subprocess


def download_youtube(url, workdir="temp"):
    os.makedirs(workdir, exist_ok=True)
    output = os.path.join(workdir, "input.mp4")
    subprocess.run(["yt-dlp", url, "-f", "mp4", "-o", output], check=True)
    return output
