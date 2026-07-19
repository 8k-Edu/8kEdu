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
    subprocess.run(["uv", "run", "analyze.py", "--backend", os.environ.get("KEDU_BACKEND", "lmstudio"),
                    "--video", video_id],
                   cwd=ROOT, timeout=1800, check=True)
    n = _upsert_from_disk(video_id)
    return {"video_id": video_id, "source": "engine", "concepts": n}


# ---------- MONITOR — new uploads on a channel ----------
def _channel_url(channel: str) -> str:
    """Accept a handle (@karpathy), a channel id (UC…), or a full URL → uploads URL."""
    if channel.startswith("http"):
        return channel
    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}/videos"
    if channel.startswith("UC"):
        return f"https://www.youtube.com/channel/{channel}/videos"
    return f"https://www.youtube.com/@{channel}/videos"


def _monitor_apify(channel_url: str, max_items: int):
    """Apify YouTube scraper — the live-data sponsor path."""
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        raise RuntimeError("no APIFY_API_TOKEN")
    payload = json.dumps({"startUrls": [{"url": channel_url}], "maxResults": max_items,
                          "type": "video"}).encode()
    req = urllib.request.Request(
        f"https://api.apify.com/v2/acts/streamers~youtube-scraper/run-sync-get-dataset-items?token={token}",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        items = json.loads(r.read())
    return [{"id": it.get("id"), "title": it.get("title")} for it in items[:max_items] if it.get("id")]


def _monitor_ytdlp(channel_url: str, max_items: int):
    """yt-dlp fallback — fast, no token; keeps the live loop resilient."""
    out = subprocess.run(
        ["uv", "run", "yt-dlp", channel_url, "--flat-playlist", f"--playlist-end={max_items}",
         "--print", "%(id)s\t%(title)s"],
        cwd=ROOT, capture_output=True, text=True, timeout=90)
    vids = []
    for line in out.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 1 and parts[0]:
            vids.append({"id": parts[0], "title": parts[1] if len(parts) > 1 else ""})
    return vids


def monitor_channel(channel: str, max_items: int = 3):
    """Recent uploads for a channel. Apify first (sponsor live-data), yt-dlp fallback."""
    url = _channel_url(channel)
    try:
        vids = _monitor_apify(url, max_items)
        if vids:
            return {"source": "apify", "videos": vids}
    except Exception as e:
        apify_err = str(e)[:120]
        try:
            vids = _monitor_ytdlp(url, max_items)
            return {"source": "yt-dlp (apify fallback)", "videos": vids, "apify_error": apify_err}
        except Exception as e2:
            return {"error": f"apify: {apify_err} | yt-dlp: {str(e2)[:120]}", "videos": []}
    return {"source": "apify", "videos": []}
