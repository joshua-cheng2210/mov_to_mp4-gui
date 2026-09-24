"""
YouTube -> audio-only .mp4 downloader.

Downloads ONLY the audio stream of a YouTube video (no video track) and saves it
as an .mp4 file in the "reel songs" folder.

How it works:
- yt-dlp picks the best AAC audio stream ("m4a"), which is already an MP4
  container, so ffmpeg just remuxes it to .mp4 (stream copy, no quality loss).
- If no AAC stream exists, it falls back to the best audio of any codec and
  re-encodes it to AAC so the .mp4 plays everywhere (phones, CapCut, Instagram).

Run:
    python "youtube audio extractor.py"                 (prompts for links)
    python "youtube audio extractor.py" URL [URL ...]   (download these links)

Requires:  pip install -U yt-dlp   and ffmpeg on PATH.
"""

import os
import sys
from shutil import which

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp is not installed. Run:  python -m pip install -U yt-dlp")

OUTPUT_DIR = r"C:\Users\Admin\Documents\joshua\joshua.getshigh instagram\reel songs"


def download_audio(urls):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    opts = {
        # Prefer AAC (m4a) so the mp4 is a lossless remux; else take any best audio.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(OUTPUT_DIR, "%(title)s.%(ext)s"),
        "windowsfilenames": True,   # strip characters Windows can't use in names
        "noplaylist": True,         # a link with &list=... downloads just that video
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "aac"},
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
        ],
        # Belt and braces: drop any video stream so the .mp4 is audio-only.
        "postprocessor_args": {"videoremuxer": ["-vn"]},
    }

    failed = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        for url in urls:
            print(f"\n==> {url}", flush=True)
            try:
                ydl.download([url])
            except Exception as e:
                print(f"FAILED: {e}", flush=True)
                failed.append(url)

    print(f"\nDone. {len(urls) - len(failed)}/{len(urls)} saved to:\n  {OUTPUT_DIR}", flush=True)
    if failed:
        print("Failed:", *failed, sep="\n  ", flush=True)


def main():
    if not which("ffmpeg"):
        sys.exit("ffmpeg was not found on PATH. It is needed to make the .mp4.")

    urls = sys.argv[1:]
    if not urls:
        print("Paste YouTube links (one per line). Press Enter on an empty line to start.")
        while True:
            line = input("> ").strip()
            if not line:
                break
            urls.append(line)

    if not urls:
        print("No links given.")
        return
    download_audio(urls)


if __name__ == "__main__":
    main()
