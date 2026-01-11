import subprocess, os

def download_youtube(url):
    os.makedirs("temp", exist_ok=True)
    output = "temp/input.mp4"
    subprocess.run(["yt-dlp", url, "-f", "mp4", "-o", output])
    return output
