#!/usr/bin/env python3
"""YouTube video downloader — downloads videos in the best available quality."""

import argparse
import sys
import os

import yt_dlp


def build_opts(output_dir: str, audio_only: bool) -> dict:
    """Build yt-dlp option dictionary."""
    os.makedirs(output_dir, exist_ok=True)

    opts = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
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
        # Best video + best audio, merged into mp4
        opts["format"] = "bestvideo+bestaudio/best"

    return opts


def download(url: str, output_dir: str = "downloads", audio_only: bool = False) -> None:
    """Download a YouTube video by URL."""
    opts = build_opts(output_dir, audio_only)

    with yt_dlp.YoutubeDL(opts) as ydl:
        print(f"Fetching info: {url}")
        info = ydl.extract_info(url, download=False)
        title = info.get("title", url)
        print(f"Downloading: {title}")
        ydl.download([url])
        print("Done!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download YouTube videos in the best available quality."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-o",
        "--output",
        default="downloads",
        help="Output directory (default: downloads)",
    )
    parser.add_argument(
        "-a",
        "--audio-only",
        action="store_true",
        help="Download audio only (saves as mp3)",
    )

    args = parser.parse_args()
    try:
        download(args.url, output_dir=args.output, audio_only=args.audio_only)
    except yt_dlp.utils.DownloadError as e:
        print(f"Download error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)


if __name__ == "__main__":
    main()
