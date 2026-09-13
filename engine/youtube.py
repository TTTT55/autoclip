import base64
import json
import os
import re
import subprocess
import tempfile


def _looks_like_netscape_cookie_file(data):
    """Return True when data looks like a Netscape/Mozilla cookie export."""
    text = data.decode("utf-8", errors="replace").lstrip("\ufeff")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Netscape cookie rows have seven tab-separated fields.
        if len(line.split("\t")) == 7:
            return True
    return False


def _json_cookies_to_netscape(data):
    """Convert common browser-extension JSON cookie exports to Netscape format."""
    text = data.decode("utf-8", errors="strict").lstrip("\ufeff").strip()
    if not text.startswith(("[", "{")):
        return None

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if isinstance(payload, dict):
        payload = payload.get("cookies")
    if not isinstance(payload, list):
        return None

    rows = ["# Netscape HTTP Cookie File"]
    converted = 0
    for cookie in payload:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get("domain")
        path = cookie.get("path", "/")
        name = cookie.get("name")
        value = cookie.get("value", "")
        if not domain or name is None:
            continue
        include_subdomains = "TRUE" if not cookie.get("hostOnly", False) else "FALSE"
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"
        expires = cookie.get("expirationDate", cookie.get("expires", 0))
        try:
            expires = int(float(expires)) if expires not in (None, "") else 0
        except (TypeError, ValueError):
            expires = 0
        rows.append(
            "\t".join(
                [
                    str(domain),
                    include_subdomains,
                    str(path),
                    secure,
                    str(expires),
                    str(name),
                    str(value),
                ]
            )
        )
        converted += 1

    return ("\n".join(rows) + "\n").encode("utf-8") if converted else None


def _normalize_cookie_bytes(cookie_bytes):
    """Accept Netscape cookies.txt and common JSON browser exports."""
    cookie_bytes = cookie_bytes.lstrip(b"\xef\xbb\xbf")

    if _looks_like_netscape_cookie_file(cookie_bytes):
        text = cookie_bytes.decode("utf-8", errors="replace").lstrip("\ufeff")
        if not text.startswith("#"):
            text = "# Netscape HTTP Cookie File\n" + text
        return text.encode("utf-8")

    converted = _json_cookies_to_netscape(cookie_bytes)
    if converted:
        return converted

    return None


def _write_cookie_secret(workdir):
    """Materialize optional GitHub Actions YouTube cookies into a temp file."""
    encoded = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
    if not encoded:
        return None

    # Base64 copied from command-line tools may contain line wrapping.
    encoded = re.sub(r"\s+", "", encoded)
    try:
        cookie_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("YOUTUBE_COOKIES_B64 is not valid base64") from exc

    normalized = _normalize_cookie_bytes(cookie_bytes)
    if normalized is None:
        raise RuntimeError(
            "YOUTUBE_COOKIES_B64 does not decode to a supported cookie export. "
            "Use a Netscape/Mozilla cookies.txt export (preferred) or a browser JSON cookie export."
        )

    fd, path = tempfile.mkstemp(prefix="youtube-cookies-", suffix=".txt", dir=workdir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(normalized)
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
