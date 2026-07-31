"""One-time catch-up: push keyframes already on this disk into Supabase Storage.

data/*/frames/ is gitignored, so every jpg here predates ingest.py's upload step and exists
on exactly one machine. Idempotent and resumable — objects upsert, rows upsert on
(video_id, t_s) — so a partial run is safe to repeat.

  uv run python scripts/backfill_frames.py --dry-run
  uv run python scripts/backfill_frames.py [--video <id>]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ingest  # noqa: E402  — owns the publish rules; this script just drives them
from agent import db, storage  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


def videos_with_frames(only: str | None) -> list[tuple[str, list[dict]]]:
    out = []
    for manifest in sorted(DATA.glob("*/frames.json")):
        vid = manifest.parent.name
        if only and vid != only:
            continue
        frames = [fr for fr in json.loads(manifest.read_text())
                  if (manifest.parent / "frames" / fr["file"]).exists()]
        if frames:
            out.append((vid, frames))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=None, help="one video id instead of everything on disk")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db.load_env()
    if not storage.enabled():
        sys.exit("storage disabled — need SUPABASE_URL + SUPABASE_SECRET_KEY, and KEDU_FRAME_REMOTE != 0")

    work = videos_with_frames(args.video)
    total = sum(len(f) for _, f in work)
    size = sum((DATA / v / "frames" / fr["file"]).stat().st_size for v, f in work for fr in f)
    print(f"{len(work)} videos / {total} frames / {size / 1048576:.1f} MB → bucket {storage.bucket_name()!r}")
    for vid, frames in work:
        print(f"  {vid:14} {len(frames):>4}")
    if args.dry_run:
        return

    done = 0

    def tick():
        nonlocal done
        done += 1
        if done % 50 == 0:
            print(f"  … {done}/{total}")

    for vid, frames in work:
        # prune=False: upserts, so a partial run is resumable without dropping what landed.
        n = ingest.upload_frames(vid, DATA / vid, frames, on_upload=tick)
        print(f"  {vid:14} {n:>4} uploaded + rows written")
    print(f"done: {done} frames across {len(work)} videos")


if __name__ == "__main__":
    main()
