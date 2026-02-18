#!/usr/bin/env python3
"""Web UI for downloading YouTube videos."""

import base64
import os
import tempfile
import threading
import uuid

from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory task tracker: task_id -> {status, progress, filename, error}
tasks: dict[str, dict] = {}

# ── Cookies ───────────────────────────────────────────────────────────

_cookies_path: str | None = None
_cookies_lock = threading.Lock()


def _init_cookies_from_env():
    raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not raw:
        return
    try:
        content = base64.b64decode(raw).decode("utf-8")
    except Exception:
        content = raw
    _write_cookies(content)


def _write_cookies(content: str):
    global _cookies_path
    with _cookies_lock:
        if _cookies_path and os.path.exists(_cookies_path):
            os.unlink(_cookies_path)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write(content)
        tmp.close()
        _cookies_path = tmp.name


_init_cookies_from_env()

# ── Download ──────────────────────────────────────────────────────────

def _make_progress_hook(task_id: str):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = int(downloaded / total * 100) if total else 0
            tasks[task_id]["progress"] = pct
        elif d["status"] == "finished":
            tasks[task_id]["progress"] = 100
    return hook


def _download_task(task_id: str, url: str, audio_only: bool):
    try:
        opts = {
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_make_progress_hook(task_id)],
        }

        # Use iOS player client — avoids bot detection without cookies for most videos
        opts["extractor_args"] = {"youtube": {"player_client": ["ios", "web"]}}

        with _cookies_lock:
            if _cookies_path and os.path.exists(_cookies_path):
                opts["cookiefile"] = _cookies_path

        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }]
        else:
            opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if audio_only:
                filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            else:
                base, ext = os.path.splitext(ydl.prepare_filename(info))
                filename = base + (".mp4" if ext != ".mp4" else ext)

            tasks[task_id]["status"] = "done"
            tasks[task_id]["filename"] = os.path.basename(filename)

    except Exception as exc:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(exc)

# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", cookies_loaded=_cookies_path is not None)


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    audio_only = data.get("audio_only", False)
    task_id = uuid.uuid4().hex[:8]
    tasks[task_id] = {"status": "downloading", "progress": 0, "filename": None, "error": None}
    threading.Thread(target=_download_task, args=(task_id, url, audio_only), daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/api/file/<filename>")
def serve_file(filename: str):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


# Cookies endpoints
@app.route("/api/cookies", methods=["POST"])
def upload_cookies():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    content = request.files["file"].read().decode("utf-8")
    if not content.strip():
        return jsonify({"error": "Empty file"}), 400
    _write_cookies(content)
    return jsonify({"ok": True})


@app.route("/api/cookies", methods=["DELETE"])
def delete_cookies():
    global _cookies_path
    with _cookies_lock:
        if _cookies_path and os.path.exists(_cookies_path):
            os.unlink(_cookies_path)
        _cookies_path = None
    return jsonify({"ok": True})


@app.route("/api/cookies/status")
def cookies_status():
    return jsonify({"loaded": _cookies_path is not None})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting YouTube Downloader at http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
