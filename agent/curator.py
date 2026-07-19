"""8kEdu curator — an autonomous heartbeat that grows the shared library.

Each tick: pick the genre with the fewest cached videos, ask Nemotron for a good search
query, find a fresh lecture, process it (ingest keyframes + analyze with that genre's lens),
and upsert into the Supabase global cache. Every video framed once is reused by every learner
→ the moat compounds on its own.

Runs alongside the learner loop; both are Claw Agents (heartbeat, autonomous, persistent).

  uv run agent/curator.py --once                 # one video
  uv run agent/curator.py --interval 300         # forever, one video every 5 min
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# allow both `python -m agent.curator` and `uv run agent/curator.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import db, brain, tools

ROOT = Path(__file__).resolve().parent.parent

# genre → the lens analyze.py applies + seed queries the agent searches within
GENRES = {
    "ai_stem":     ["neural network explained", "backpropagation visualized", "transformer architecture", "gradient descent intuition"],
    "how_to":      ["how to tie a tie step by step", "how to change a tire", "how to make espresso at home", "how to fold a fitted sheet"],
    "cooking":     ["perfect risotto recipe", "how to make pizza dough", "french omelette technique", "homemade pasta recipe"],
    "finance":     ["compound interest explained", "how index funds work", "bond yields explained", "options trading basics"],
    "real_estate": ["how mortgages work", "rent vs buy analysis", "real estate cash flow explained", "house hacking explained"],
    "fitness":     ["progressive overload explained", "how to calculate macros", "couch to 5k plan", "hypertrophy training basics"],
}

PICK_SYSTEM = (
    "You are 8kEdu's library curator. Given a genre and some example search phrases, output ONE "
    "specific, high-quality YouTube search query likely to return a clear educational lecture in "
    'that genre. Reply with JSON only: {"query": <string>}.'
)


def pick_query(genre):
    """Nemotron proposes a search query for the genre; fall back to a seed if the model is down."""
    seeds = GENRES[genre]
    try:
        d = brain.decide(PICK_SYSTEM, f'Genre: {genre}. Examples: {seeds}. Give one query.')
        q = (d.get("query") or "").strip()
        if q:
            return q
    except Exception:
        pass
    # rotate seeds deterministically by how many videos already cached in this genre
    n = next((g["videos"] for g in db.library_stats() if g["genre"] == genre), 0)
    return seeds[n % len(seeds)]


def least_filled_genre():
    stats = {g["genre"]: g["videos"] for g in db.library_stats()}
    return min(GENRES, key=lambda g: stats.get(g, 0))


def process_new(video_id, genre, title="", channel=""):
    """Cold path: ingest keyframes + analyze with the genre lens → Supabase cache.
    host uses `uv run`; the OpenShell sandbox has no uv, so fall back to bare python3."""
    import shutil
    runner = ["uv", "run"] if shutil.which("uv") else ["python3"]
    vd = ROOT / "data" / video_id
    if not (vd / "frames.json").exists():
        subprocess.run(runner + ["ingest.py", f"https://www.youtube.com/watch?v={video_id}"],
                       cwd=ROOT, timeout=900, check=True)
    subprocess.run(runner + ["analyze.py", "--backend", os.environ.get("KEDU_BACKEND", "lmstudio"),
                    f"--video={video_id}", "--genre", genre, "--limit", "16",  # = form: IDs can start with '-'
                    "--recursive-topic", genre, "--recursive-mode", "warm", "--max-px", "512"],
                   cwd=ROOT, timeout=2400, check=True)
    n = tools._upsert_from_disk(video_id)
    db.set_video_genre(video_id, genre, title, channel)
    return n


def tick():
    genre = least_filled_genre()
    query = pick_query(genre)
    decided = {"action": "CURATE", "genre": genre, "query": query, "why": f"grow {genre} library"}
    actions = {}
    status = "ok"
    try:
        candidates = tools.find_video(query, 5)
        fresh = next((v for v in candidates if not db.is_cached(v["id"])), None)
        if not fresh:
            actions = {"genre": genre, "query": query, "note": "no fresh video (all cached)"}
        else:
            n = process_new(fresh["id"], genre, fresh.get("title", ""), fresh.get("channel", ""))
            actions = {"genre": genre, "query": query, "video_id": fresh["id"],
                       "title": fresh["title"][:60], "widgets": n}
    except Exception as e:
        status = "error"
        actions = {"genre": genre, "query": query, "error": str(e)[:160]}

    try:
        # log under a distinct system learner so it shows on the dashboard without polluting a course
        uid = db.ensure_learner("curator")
        db.log_run(uid, "curator", decided, actions, status)
    except Exception as e:
        print("[curator] log failed:", str(e)[:100])
    print(f"[curator] {genre:12} [{status}] {str(actions)[:100]}")
    return actions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()
    print("curator up · genres:", ", ".join(GENRES))
    if args.once:
        tick()
        return
    while True:
        try:
            tick()
        except Exception as e:
            print("[curator] tick error:", str(e)[:120])
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
