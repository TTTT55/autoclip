import gdown, os

def download_drive(url):
    os.makedirs("temp", exist_ok=True)
    output = "temp/input.mp4"
    gdown.download(url, output, quiet=False)
    return output
