import os

import gdown


def download_drive(url, workdir="temp"):
    os.makedirs(workdir, exist_ok=True)
    output = os.path.join(workdir, "input.mp4")
    result = gdown.download(url, output, quiet=False)
    if not result:
        raise RuntimeError("Google Drive download failed")
    return output
