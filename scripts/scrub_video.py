"""Completely remove one video from Supabase + local disk, for cold re-testing.

    uv run python scripts/scrub_video.py <video_id> [--yes]

Deletes every row keyed to the video across all tables and the data/<video_id>/
directory. Restart serve.py afterward if it was running — it memoizes frames.json
per video in-process.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import db

ROOT = Path(__file__).resolve().parent.parent

# child → parent: curriculum has a RESTRICT fk to videos, so videos must go last.
_DELETE_BY_VIDEO = [
    "widget_events", "inference_cache", "artifacts_pub",
    "concepts", "frames", "transcripts", "curriculum", "videos",
]


def scrub(video_id: str) -> dict:
    counts = {}
    with db.conn() as c, c.cursor() as cur:
        cur.execute("update paths set video_ids = array_remove(video_ids, %s) "
                    "where %s = any(video_ids)", (video_id, video_id))
        counts["paths (video removed)"] = cur.rowcount
        for table in _DELETE_BY_VIDEO:
            cur.execute(f"delete from {table} where video_id = %s", (video_id,))
            counts[table] = cur.rowcount
        c.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()
    vid = args.video_id

    local = ROOT / "data" / vid
    print(f"scrubbing {vid!r} — DB rows + {local}")
    if not args.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted.")
            return

    counts = scrub(vid)
    for table, n in counts.items():
        print(f"  db  {table:<22} {n}")

    if local.exists():
        shutil.rmtree(local)
        print(f"  fs  removed {local}")
    else:
        print(f"  fs  {local} (absent)")

    print("done — cold. restart serve.py if it was running (in-process frames cache).")


if __name__ == "__main__":
    main()
