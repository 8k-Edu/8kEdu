"""Agent tools — the capabilities the heartbeat can invoke.
Each is a plain function; the loop calls them based on Nemotron's decision.
Network + exec here are what OpenShell contains.
"""
import json
import os
import subprocess
from pathlib import Path
import urllib.request
from agent import db

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


# ---------- FIND_VIDEO — discover a lecture for a concept ----------
def find_video(query: str, n: int = 3):
    """YouTube search via yt-dlp (fast, reliable for the live loop)."""
    out = subprocess.run(
        ["uv", "run", "yt-dlp", f"ytsearch{n}:{query}", "--flat-playlist",
         "--print", "%(id)s\t%(title)s\t%(channel)s"],
        cwd=ROOT, capture_output=True, text=True, timeout=90)
    vids = []
    for line in out.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            vids.append({"id": parts[0], "title": parts[1],
                         "channel": parts[2] if len(parts) > 2 else ""})
    return vids


# ---------- PROCESS_VIDEO — turn a video into interactive widgets (cache-aware) ----------
def _cache_count(video_id: str):
    with db.conn() as c, c.cursor() as cur:
        cur.execute("select count(*) from concepts where video_id=%s", (video_id,))
        return cur.fetchone()[0]


def _upsert_from_disk(video_id: str):
    """Fill the Supabase global cache from a locally-processed video."""
    vd = DATA / video_id
    concepts = json.loads((vd / "concepts.json").read_text())
    title = ""
    with db.conn() as c, c.cursor() as cur:
        cur.execute("insert into videos(video_id,title) values (%s,%s) on conflict (video_id) do nothing",
                    (video_id, title))
        cur.execute("delete from concepts where video_id=%s", (video_id,))
        for cc in concepts:
            cur.execute("insert into concepts(video_id,t_s,widget,spec,model) values (%s,%s,%s,%s,%s)",
                        (video_id, cc.get("time"), cc.get("widget"), json.dumps(cc),
                         "nemotron-3-nano-omni"))
        c.commit()
    return len(concepts)


def process_video(video_id: str):
    """1) Supabase cache hit → reuse (the moat). 2) local disk → fill cache. 3) run engine."""
    n = _cache_count(video_id)
    if n:
        return {"video_id": video_id, "source": "supabase-cache", "concepts": n, "reused": True}
    if (DATA / video_id / "concepts.json").exists():
        n = _upsert_from_disk(video_id)
        return {"video_id": video_id, "source": "disk→cache", "concepts": n}
    # cold: run the engine (ingest + analyze). Slow; used for genuinely new videos.
    subprocess.run(["uv", "run", "ingest.py", f"https://www.youtube.com/watch?v={video_id}"],
                   cwd=ROOT, timeout=600, check=True)
    subprocess.run(["uv", "run", "analyze.py", "--backend", "lmstudio", "--video", video_id],
                   cwd=ROOT, timeout=1800, check=True)
    n = _upsert_from_disk(video_id)
    return {"video_id": video_id, "source": "engine", "concepts": n}


# ---------- MONITOR — new uploads on a channel (Apify: the live-data sponsor use) ----------
def monitor_channel(channel_url: str, max_items: int = 3):
    token = os.environ.get("APIFY_API_TOKEN", "")
    payload = json.dumps({"startUrls": [{"url": channel_url}], "maxResults": max_items,
                          "type": "video"}).encode()
    req = urllib.request.Request(
        f"https://api.apify.com/v2/acts/streamers~youtube-scraper/run-sync-get-dataset-items?token={token}",
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            items = json.loads(r.read())
        return [{"id": it.get("id"), "title": it.get("title")} for it in items[:max_items]]
    except Exception as e:
        return {"error": str(e)[:160]}
