import base64
import os
import re
import subprocess
import tempfile


def _write_cookie_secret(workdir):
    """Materialize optional GitHub Actions YouTube cookies into a temp file."""
    encoded = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
    if not encoded:
        return None

    # Base64 copied from some command-line tools may contain line wrapping.
    # Ignore whitespace so both wrapped and single-line secrets work.
    encoded = re.sub(r"\s+", "", encoded)
    try:
        cookie_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("YOUTUBE_COOKIES_B64 is not valid base64") from exc

    # Some editors/exporters add a UTF-8 BOM before the Netscape header.
    cookie_bytes = cookie_bytes.lstrip(b"\xef\xbb\xbf")
    if not cookie_bytes.startswith((b"# HTTP Cookie File", b"# Netscape HTTP Cookie File")):
        raise RuntimeError(
            "YOUTUBE_COOKIES_B64 does not contain a Netscape/Mozilla cookie file. "
            "Export the cookies as a Netscape/Mozilla cookies.txt file and base64-encode that file."
        )

    fd, path = tempfile.mkstemp(prefix="youtube-cookies-", suffix=".txt", dir=workdir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(cookie_bytes)
        os.chmod(path, 0o600)
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def download_youtube(url, workdir="temp"):
    os.makedirs(workdir, exist_ok=True)
    output = os.path.join(workdir, "input.mp4")
    cookie_file = _write_cookie_secret(workdir)

    # GitHub-hosted runners use datacenter IPs that YouTube may challenge.
    # Keep the no-cookie client path for videos that allow it, but support an
    # optional user-provided YouTube cookie jar for challenged requests.
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
    if cookie_file:
        command[1:1] = ["--cookies", cookie_file]

    try:
        subprocess.run(command, check=True)
    finally:
        if cookie_file:
            try:
                os.unlink(cookie_file)
            except OSError:
                pass

    return output
