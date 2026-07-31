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
import tempfile

# host uses `uv run yt-dlp`; the sandbox has yt-dlp on PATH but no uv
YTDLP = ["uv", "run", "yt-dlp"] if shutil.which("uv") else ["yt-dlp"]
# inside the OpenShell sandbox, TLS is MITM'd by the egress proxy (which is the real security
# boundary — it allowlists youtube/googlevideo); yt-dlp's certifi doesn't trust that CA.
if os.environ.get("KEDU_SANDBOX") == "1":
    YTDLP = YTDLP + ["--no-check-certificates"]
from pathlib import Path

MAX_FRAMES = 120
FRAME_HEIGHT = 720  # enough for VLM to read code/equations


def run(cmd: list[str], check: bool = True, timeout: int | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, timeout=timeout).returncode


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


FRAME_LEAD_S = 2  # section starts this far before the target so the cut lands on a keyframe


def fetch_one_frame(vid: str, t_s: float, frame_file: str, frames_dir: Path,
                    timeout: int | None = 60) -> Path | None:
    """One keyframe from YouTube, for a moment whose jpg exists nowhere.

    Mirrors download()'s 480p selector and extract_frames()' recipe: the library is 480p
    upscaled to 720, so a sharper source would read differently to the VLM. frame_file must
    come from the manifest — `time` is round(sec, 1) while the filename is int(sec)."""
    start = max(0.0, t_s - FRAME_LEAD_S)
    dest = frames_dir / frame_file
    try:
        frames_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            run(YTDLP + [
                "--download-sections", f"*{start}-{t_s + 5}",
                "--force-keyframes-at-cuts",
                "-f", "bv*[height<=480]+ba/b[height<=480]/b",
                "-o", str(Path(td) / "clip.%(ext)s"),
                f"https://www.youtube.com/watch?v={vid}",
            ], timeout=timeout)
            clips = sorted(Path(td).glob("clip.*"))
            if not clips:
                return None
            # --force-keyframes-at-cuts makes the clip start at `start`, so the seek into it
            # is the lead-in, never the absolute timestamp.
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t_s - start),
                 "-i", str(clips[0]), "-frames:v", "1",
                 "-vf", f"scale=-2:{FRAME_HEIGHT}", "-q:v", "3", str(dest)], timeout=timeout)
        return dest if dest.exists() and dest.stat().st_size else None
    except Exception as e:
        print(f"! frame recovery failed for {vid}@{t_s}: {e}")
        return None


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


def _publish_plan(published: dict, wanted: dict, on_disk: set) -> tuple[list, list, list]:
    """(to_upload, to_remove, gone), keyed on t_s — the frames primary key. Pure, so the
    reconcile reads without a bucket in the way. Reconciling beats pruning: a frame recovered
    on demand is already analyzed under its filename, so only keys the new manifest has truly
    orphaned land in to_remove."""
    to_upload, stale = [], []
    for t_s, name in wanted.items():
        previous = published.get(t_s)
        if name not in on_disk or (previous and previous.rsplit("/", 1)[-1] == name):
            continue
        if previous:
            stale.append(previous)
        to_upload.append((t_s, name))
    gone = [t_s for t_s in published if t_s not in wanted]
    return to_upload, stale + [published[t_s] for t_s in gone], gone


def upload_frames(vid: str, out: Path, frames: list[dict], on_upload=None) -> int:
    """Publish `frames`, uploading only what isn't there already. Raises — callers decide
    what's fatal. scripts/backfill_frames.py drives this too."""
    from agent import db, storage
    db.load_env()  # `uv run ingest.py <url>` sources no .env of its own
    if not storage.enabled():
        return 0
    storage.ensure_bucket()

    frames_dir = out / "frames"
    to_upload, to_remove, gone = _publish_plan(
        db.frames_rows(vid), {fr["time"]: fr["file"] for fr in frames},
        {p.name for p in frames_dir.glob("*.jpg")})

    rows = []
    for t_s, name in to_upload:
        rows.append((t_s, storage.upload_frame(vid, frames_dir / name)))
        if on_upload:
            on_upload()
    storage.remove_objects(to_remove)
    db.delete_frames_at(vid, gone)
    db.upsert_frames(vid, rows)
    return len(rows)


def publish_frames(vid: str, out: Path, frames: list[dict]) -> int:
    """Best-effort upload_frames: a failed publish must not fail an ingest whose local analyze
    works either way. Not in extract_frames(), which never learns the video id."""
    if os.environ.get("KEDU_FRAME_REMOTE") == "0":
        return 0
    try:
        return upload_frames(vid, out, frames)
    except Exception as e:
        print(f"! frame upload skipped: {e}")
        return 0


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
    published = publish_frames(video_id(args.url), out, frames)
    print(f"done: {len(cues)} cues, {len(frames)} frames, {len(chapters)} chapters, "
          f"{published} frames published → {out}/")


if __name__ == "__main__":
    main()
