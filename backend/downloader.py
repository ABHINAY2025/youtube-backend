"""yt-dlp wrapper: format probing + background download jobs with progress."""
import concurrent.futures
import glob
import os
import random
import re
import shutil
import threading
import time
import uuid

from yt_dlp import YoutubeDL

from config import PROXIES, YTDLP_COOKIES

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _find_ffmpeg():
    env = os.environ.get("FFMPEG_LOCATION")
    if env and os.path.isdir(env):
        return env
    if env and os.path.isfile(env):
        return os.path.dirname(env)
    found = shutil.which("ffmpeg")
    if found:
        return os.path.dirname(found)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        hits = glob.glob(os.path.join(
            local, "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"), recursive=True)
        if hits:
            return os.path.dirname(hits[0])
    return None


FFMPEG_DIR = _find_ffmpeg()
FFMPEG_AVAILABLE = FFMPEG_DIR is not None
if FFMPEG_DIR:
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# True when at least one proxy is set — tailors the "blocked" message + UI banner.
PROXY_CONFIGURED = bool(PROXIES)


def _proxy_candidates():
    """Proxies to try, in random order; [None] means a direct connection."""
    if not PROXIES:
        return [None]
    pool = list(PROXIES)
    random.shuffle(pool)
    return pool


def _is_blocked(err):
    """True when the error looks like an IP/proxy block worth retrying elsewhere."""
    low = str(err).lower()
    return any(s in low for s in (
        "not a bot", "sign in to confirm", "http error 429", "too many requests",
        "video unavailable", "this content isn", "unable to download api page",
        "ssl", "eof occurred", "timed out", "connection reset", "failed to extract",
    ))


def friendly_error(raw):
    """Turn a raw yt-dlp error into a clear, user-facing message."""
    msg = str(raw)
    low = msg.lower()
    blocked = any(s in low for s in (
        "sign in to confirm", "not a bot", "http error 429", "too many requests",
        "unable to download api page", "ssl", "eof occurred", "read timed out",
        "failed to extract any player response", "connection reset", "timed out",
    ))
    if blocked:
        if PROXY_CONFIGURED:
            return ("YouTube is rate-limiting the server right now. Please try "
                    "again in a moment.")
        return ("Downloads are temporarily unavailable: YouTube is blocking this "
                "server's IP. The site owner needs to configure a proxy "
                "(YTDLP_PROXY) to enable downloads.")
    if "private video" in low:
        return "This is a private video and can't be downloaded."
    if "video unavailable" in low or "removed" in low:
        return "This video is unavailable or has been removed."
    if "age" in low and "confirm" in low:
        return "This video is age-restricted and needs sign-in cookies to download."
    # Fall back to a trimmed version of the raw error.
    short = msg.split("; please report")[0].strip()
    return f"Could not process this link: {short[:200]}"

# In-memory job table. NOTE: this requires the server to run as a single
# worker (gunicorn -w 1 --threads N). See README for the scaling path.
JOBS = {}
JOBS_LOCK = threading.Lock()


def _base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # Fail fast instead of hanging when the host IP is blocked.
        "socket_timeout": 10,
        "retries": 1,
        "extractor_retries": 1,
        "fragment_retries": 1,
    }
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    if YTDLP_COOKIES and os.path.isfile(YTDLP_COOKIES):
        opts["cookiefile"] = YTDLP_COOKIES
    return opts


def _sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    return name.strip().rstrip(".")[:150] or "video"


def _human_size(num):
    if not num:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


# Bounds the synchronous /api/info call. With proxies we try several, so the
# cap is larger; without, it stays tight so a blocked host fails fast.
PROBE_TIMEOUT = 16
PROBE_TIMEOUT_PROXIED = 35
_PROBE_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def probe(url):
    """Probe with a hard wall-clock cap; raises a friendly error on timeout."""
    timeout = PROBE_TIMEOUT_PROXIED if PROXIES else PROBE_TIMEOUT
    future = _PROBE_POOL.submit(_probe, url)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        # The yt-dlp thread keeps running in the background and will exit on
        # its own once its socket timeouts fire; we just stop waiting.
        raise ValueError(friendly_error("read timed out")) from exc


def _probe(url):
    """Return metadata + qualities, rotating proxies until one isn't blocked."""
    last = None
    for proxy in _proxy_candidates():
        opts = {**_base_opts(), "skip_download": True}
        if proxy:
            opts["proxy"] = proxy
        try:
            with YoutubeDL(opts) as ydl:
                data = ydl.extract_info(url, download=False)
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            if proxy and _is_blocked(exc):
                continue  # this proxy is blocked; try the next one
            raise ValueError(friendly_error(exc)) from exc
    else:
        raise ValueError(friendly_error(last))

    if data.get("_type") == "playlist":
        entries = [e for e in data.get("entries", []) if e]
        if not entries:
            raise ValueError("Empty playlist.")
        data = entries[0]

    video_q, progressive = {}, {}
    for f in data.get("formats", []):
        h, vcodec, acodec = f.get("height"), f.get("vcodec"), f.get("acodec")
        if not h or vcodec in (None, "none"):
            continue
        has_audio = acodec not in (None, "none")
        entry = {
            "format_id": f.get("format_id"), "height": h, "ext": f.get("ext"),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "tbr": f.get("tbr"),
        }
        if has_audio:
            cur = progressive.get(h)
            if not cur or (entry["ext"] == "mp4" and cur["ext"] != "mp4"):
                progressive[h] = entry
        cur = video_q.get(h)
        if not cur or (f.get("tbr") or 0) > (cur.get("tbr") or 0):
            video_q[h] = entry

    qualities = []
    for h in sorted(video_q, reverse=True):
        if FFMPEG_AVAILABLE:
            qualities.append({
                "label": f"{h}p", "height": h, "mode": "merge",
                "format_id": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                "filesize": _human_size(video_q[h].get("filesize")),
            })
        elif h in progressive:
            qualities.append({
                "label": f"{h}p", "height": h, "mode": "progressive",
                "format_id": progressive[h]["format_id"],
                "filesize": _human_size(progressive[h].get("filesize")),
            })

    return {
        "title": data.get("title"),
        "uploader": data.get("uploader"),
        "duration": data.get("duration"),
        "thumbnail": data.get("thumbnail"),
        "qualities": qualities,
        "ffmpeg": FFMPEG_AVAILABLE,
    }


def _set(job_id, **fields):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def _worker(job_id, url, fmt, mode, job_dir, on_success):
    def progress_hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else None
            _set(job_id, status="downloading",
                 progress=round(pct, 1) if pct is not None else None,
                 speed=_human_size(d.get("speed")), eta=d.get("eta"),
                 phase="Downloading")
        elif d.get("status") == "finished":
            _set(job_id, status="processing", progress=100, phase="Processing")

    def pp_hook(d):
        if d.get("status") == "started":
            _set(job_id, status="processing", phase="Merging audio + video")

    def build_opts(proxy):
        o = {
            **_base_opts(),
            "outtmpl": os.path.join(job_dir, "%(title)s.%(ext)s"),
            "format": fmt,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [pp_hook],
        }
        if proxy:
            o["proxy"] = proxy
        if mode == "audio":
            o["format"] = "bestaudio/best"
            o["postprocessors"] = [{
                "key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                "preferredquality": "192"}]
        elif mode == "merge" and FFMPEG_AVAILABLE:
            o["merge_output_format"] = "mp4"
        return o

    # Try proxies in turn; a blocked proxy rolls over to the next one.
    title, last = None, None
    for proxy in _proxy_candidates():
        try:
            with YoutubeDL(build_opts(proxy)) as ydl:
                info = ydl.extract_info(url, download=True)
                title = _sanitize_filename(info.get("title", "video"))
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            # Clear any partial fragments before retrying on another proxy.
            for f in os.listdir(job_dir):
                try:
                    os.remove(os.path.join(job_dir, f))
                except OSError:
                    pass
            if proxy and _is_blocked(exc):
                _set(job_id, status="starting", phase="Switching route…")
                continue
            shutil.rmtree(job_dir, ignore_errors=True)
            _set(job_id, status="error", error=friendly_error(exc))
            return
    else:
        shutil.rmtree(job_dir, ignore_errors=True)
        _set(job_id, status="error", error=friendly_error(last))
        return

    files = [f for f in os.listdir(job_dir)
             if os.path.isfile(os.path.join(job_dir, f))]
    if not files:
        shutil.rmtree(job_dir, ignore_errors=True)
        _set(job_id, status="error", error="No file produced.")
        return

    filepath = os.path.join(job_dir, files[0])
    ext = os.path.splitext(files[0])[1]
    _set(job_id, status="ready", progress=100, phase="Ready",
         filepath=filepath, download_name=f"{title}{ext}", job_dir=job_dir)
    if on_success:
        try:
            on_success()  # record quota usage only when the file is ready
        except Exception:  # noqa: BLE001 - never fail the download on bookkeeping
            pass


def start_job(url, fmt, mode, on_success=None):
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "starting", "progress": 0, "phase": "Starting",
                        "speed": None, "eta": None, "error": None}
    threading.Thread(target=_worker,
                     args=(job_id, url, fmt, mode, job_dir, on_success),
                     daemon=True).start()
    return job_id


def get_job(job_id):
    with JOBS_LOCK:
        return JOBS.get(job_id)


def public_job(job_id):
    job = get_job(job_id)
    if not job:
        return None
    return {k: v for k, v in job.items() if k not in ("filepath", "job_dir")}


def schedule_cleanup(job_id, delay=120):
    def _rm():
        time.sleep(delay)
        job = get_job(job_id)
        if job and job.get("job_dir"):
            shutil.rmtree(job["job_dir"], ignore_errors=True)
        with JOBS_LOCK:
            JOBS.pop(job_id, None)

    threading.Thread(target=_rm, daemon=True).start()
