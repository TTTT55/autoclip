import os
import subprocess


def download_youtube(url, workdir="temp"):
    os.makedirs(workdir, exist_ok=True)
    output = os.path.join(workdir, "input.mp4")

    # YouTube increasingly challenges GitHub/datacenter IPs. Use clients that
    # currently work without account cookies/PO tokens and skip the initial
    # webpage request, which is a common source of the bot-check response.
    extractor_args = (
        "youtube:player_client=tv,android_vr,web_embedded;"
        "player_skip=webpage"
    )
    command = [
        "yt-dlp",
        url,
        "--extractor-args",
        extractor_args,
        "-f",
        "bestvideo*+bestaudio/best",
        "--merge-output-format",
        "mp4",
        "-o",
        output,
    ]

    subprocess.run(command, check=True)
    return output
