"""Ingest a YouTube lecture: video + transcript + keyframes.

Usage: uv run ingest.py <youtube_url_or_id> [--out data]
Outputs: <out>/video.mp4, <out>/transcript.json, <out>/frames/f_<sec>.jpg
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# host uses `uv run yt-dlp`; the sandbox has yt-dlp on PATH but no uv
YTDLP = ["uv", "run", "yt-dlp"] if shutil.which("uv") else ["yt-dlp"]
# inside the OpenShell sandbox, TLS is MITM'd by the egress proxy (which is the real security
# boundary — it allowlists youtube/googlevideo); yt-dlp's certifi doesn't trust that CA.
if os.environ.get("KEDU_SANDBOX") == "1":
    YTDLP = YTDLP + ["--no-check-certificates"]
from pathlib import Path

MAX_FRAMES = 120
FRAME_HEIGHT = 720  # enough for VLM to read code/equations


def run(cmd: list[str], check: bool = True) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check).returncode


def download(url: str, out: Path) -> Path:
    """Video is required (merge to mkv — always works); subs are best-effort."""
    existing = sorted(out.glob("video.mp4")) + sorted(out.glob("video.mkv")) + sorted(out.glob("video.webm"))
    if not existing:
        run(YTDLP + [
            "-f", "bv*[height<=480]+ba/b[height<=480]/b",
            "--merge-output-format", "mkv",
            "-o", str(out / "video.%(ext)s"),
            url,
        ])
        # subs: separate, non-fatal — many videos have none
        run(YTDLP + [
            "--skip-download",
            "--write-auto-subs", "--write-subs", "--sub-langs", "en.*",
            "-o", str(out / "video.%(ext)s"), url,
        ], check=False)
    found = sorted(out.glob("video.mp4")) + sorted(out.glob("video.mkv")) + sorted(out.glob("video.webm"))
    return found[0]


def parse_vtt(out: Path) -> list[dict]:
    """VTT → [{start: sec, end: sec, text}], deduped rolling captions."""
    vtts = sorted(out.glob("video*.vtt"))
    if not vtts:
        print("! no subtitles — continuing with frames only (empty transcript)")
        return []
    ts = re.compile(
        r"(\d+):(\d+):(\d+)\.(\d+)\s*-->\s*(\d+):(\d+):(\d+)\.(\d+)"
    )
    cues = []
    for block in vtts[0].read_text().split("\n\n"):
        m = ts.search(block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        # drop the rest of the timestamp line (cue settings like align/position)
        lines = block[m.end():].splitlines()[1:] or block[m.end():].splitlines()
        clean = [re.sub(r"<[^>]+>", "", ln).strip() for ln in lines]
        clean = [ln for ln in clean if ln]
        if not clean:
            continue
        # rolling auto-subs: first line repeats the previous cue — keep the last line
        text = clean[-1]
        if cues and (text == cues[-1]["text"] or not text):
            continue
        cues.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return cues


def duration_sec(video: Path) -> float:
    if shutil.which("ffprobe"):
        p = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, check=True,
        )
        return float(p.stdout.strip())
    # sandbox: only ffmpeg (via imageio-ffmpeg) — parse "Duration: HH:MM:SS.ss" from its stderr
    p = subprocess.run(["ffmpeg", "-i", str(video)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", p.stderr)
    if not m:
        return float(MAX_FRAMES * 10)  # unknown → default sampling cadence
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def extract_frames(video: Path, out: Path) -> list[dict]:
    """Uniform sampling: MAX_FRAMES frames, timestamp = index * interval."""
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    for old in frames_dir.glob("*.jpg"):
        old.unlink()
    dur = duration_sec(video)
    interval = max(dur / MAX_FRAMES, 10)
    run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps=1/{interval},scale=-2:{FRAME_HEIGHT}",
        "-q:v", "3",
        str(frames_dir / "seq_%06d.jpg"),
    ])
    meta = []
    for i, raw in enumerate(sorted(frames_dir.glob("seq_*.jpg"))):
        sec = i * interval  # fps filter emits first frame at t≈0, then every interval
        final = frames_dir / f"f_{int(sec):06d}.jpg"
        raw.rename(final)
        meta.append({"time": round(sec, 1), "file": final.name})
    return meta


def fetch_chapters(url: str, out: Path) -> list[dict]:
    p = subprocess.run(
        YTDLP + ["--skip-download", "--print", "%(chapters)j", url],
        capture_output=True, text=True,
    )
    try:
        raw = json.loads(p.stdout.strip() or "null") or []
    except json.JSONDecodeError:
        raw = []
    chapters = [
        {"start": c["start_time"], "end": c.get("end_time"), "title": c["title"]}
        for c in raw
    ]
    (out / "chapters.json").write_text(json.dumps(chapters, indent=1))
    return chapters


def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|embed/)([\w-]{11})", url) or re.match(r"^([\w-]{11})$", url)
    if not m:
        sys.exit(f"can't parse video id from {url}")
    return m.group(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default=None, help="default: data/<videoId>")
    args = ap.parse_args()
    out = Path(args.out) if args.out else Path("data") / video_id(args.url)
    out.mkdir(parents=True, exist_ok=True)

    video = download(args.url, out)
    cues = parse_vtt(out)
    frames = extract_frames(video, out)
    chapters = fetch_chapters(args.url, out)

    (out / "transcript.json").write_text(json.dumps(cues, indent=1))
    (out / "frames.json").write_text(json.dumps(frames, indent=1))
    print(f"done: {len(cues)} cues, {len(frames)} frames, {len(chapters)} chapters → {out}/")


if __name__ == "__main__":
    main()
