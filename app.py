#!/usr/bin/env python3
"""Web UI for downloading YouTube videos."""

import os
import uuid
import threading

from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory task tracker: task_id -> {status, progress, filename, error}
tasks: dict[str, dict] = {}


def _make_progress_hook(task_id: str):
    """Return a yt-dlp progress hook that updates task state."""
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
    """Background download worker."""
    try:
        opts = {
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_make_progress_hook(task_id)],
        }

        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ]
        else:
            opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Determine the final filename on disk
            if audio_only:
                filename = ydl.prepare_filename(info)
                filename = os.path.splitext(filename)[0] + ".mp3"
            else:
                filename = ydl.prepare_filename(info)
                # after merge the extension may have changed to mp4
                base, ext = os.path.splitext(filename)
                if ext != ".mp4":
                    filename = base + ".mp4"

            tasks[task_id]["status"] = "done"
            tasks[task_id]["filename"] = os.path.basename(filename)

    except Exception as exc:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(exc)


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    audio_only = data.get("audio_only", False)
    task_id = uuid.uuid4().hex[:8]
    tasks[task_id] = {"status": "downloading", "progress": 0, "filename": None, "error": None}

    thread = threading.Thread(target=_download_task, args=(task_id, url, audio_only), daemon=True)
    thread.start()

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


if __name__ == "__main__":
    print("Starting YouTube Downloader at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
