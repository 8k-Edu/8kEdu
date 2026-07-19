"""Supabase writes over PostgREST (HTTPS) — the DB path for the contained sandbox.

Raw Postgres can't traverse OpenShell's SNI egress proxy (postgres sends a plaintext
SSLRequest before TLS, so the proxy never sees a host to allowlist). The REST API is plain
HTTPS — SNI + Host header present — so it passes the same `supabase` policy that already
allows the REST host. Same public function names as db.py; db.py swaps to these when
KEDU_DB_REST=1, so agent/loop.py, curator.py and tools.py run unchanged inside the sandbox.

Uses only urllib (no psycopg2/httpx) so the sandbox needs nothing extra installed.
"""
import json
import os
import urllib.parse
import urllib.request

_BASE = None
_HEADERS = None


def _cfg():
    global _BASE, _HEADERS
    if _BASE is None:
        url = os.environ["SUPABASE_URL"].rstrip("/")
        key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_PUBLISHABLE_KEY"]
        _BASE = f"{url}/rest/v1"
        _HEADERS = {"apikey": key, "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"}
    return _BASE, _HEADERS


def _req(method, path, params=None, body=None, prefer=None):
    base, headers = _cfg()
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    h = dict(headers)
    if prefer:
        h["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path + q, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode()
    return json.loads(txt) if txt.strip() else []


def _select(table, where=None, select="*", limit=None, order=None):
    p = {"select": select}
    for k, v in (where or {}).items():
        p[k] = f"eq.{v}"
    if order:
        p["order"] = order
    if limit:
        p["limit"] = limit
    return _req("GET", f"/{table}", params=p)


def _insert(table, row, prefer="return=representation"):
    out = _req("POST", f"/{table}", body=row, prefer=prefer)
    return out[0] if isinstance(out, list) and out else out


def _update(table, where, patch):
    p = {k: f"eq.{v}" for k, v in where.items()}
    return _req("PATCH", f"/{table}", params=p, body=patch, prefer="return=representation")


def _delete(table, where):
    p = {k: f"eq.{v}" for k, v in where.items()}
    return _req("DELETE", f"/{table}", params=p)


# ---------- learners / goals ----------
def ensure_learner(handle="demo"):
    rows = _select("learners", {"handle": handle}, "user_id")
    if rows:
        return rows[0]["user_id"]
    return _insert("learners", {"handle": handle})["user_id"]


def set_goal(user_id, goal_text):
    rows = _select("goals", {"user_id": user_id, "goal_text": goal_text, "status": "active"}, "id")
    if rows:
        return rows[0]["id"]
    return _insert("goals", {"user_id": user_id, "goal_text": goal_text})["id"]


def active_goal(user_id):
    rows = _req("GET", "/goals", params={"select": "*", "user_id": f"eq.{user_id}",
                                         "status": "eq.active", "order": "created_at", "limit": 1})
    return rows[0] if rows else None


# ---------- videos / concepts ----------
def ensure_video(video_id, title="", channel_name=""):
    row = {"video_id": video_id, "title": title, "channel_name": channel_name}
    _insert("videos", row, prefer="resolution=merge-duplicates")


def set_video_genre(video_id, genre, title="", channel_name=""):
    ensure_video(video_id, title, channel_name)
    _update("videos", {"video_id": video_id}, {"genre": genre})


def concepts_count(video_id):
    rows = _select("concepts", {"video_id": video_id}, "id")
    return len(rows)


def is_cached(video_id):
    return concepts_count(video_id) > 0


def upsert_concepts(video_id, concepts, model="nemotron-3-nano-omni", title=""):
    ensure_video(video_id, title)
    _delete("concepts", {"video_id": video_id})
    if concepts:
        rows = [{"video_id": video_id, "t_s": c.get("time"), "widget": c.get("widget"),
                 "spec": c, "model": model} for c in concepts]
        _req("POST", "/concepts", body=rows)
    return len(concepts)


# ---------- curriculum ----------
def curriculum(goal_id):
    return _req("GET", "/curriculum", params={"select": "*", "goal_id": f"eq.{goal_id}", "order": "seq"})


def add_to_curriculum(goal_id, video_id, rationale, title="", channel_name=""):
    ensure_video(video_id, title, channel_name)
    if _select("curriculum", {"goal_id": goal_id, "video_id": video_id}, "id"):
        return False
    existing = _select("curriculum", {"goal_id": goal_id}, "seq")
    seq = max([r["seq"] for r in existing], default=0) + 1
    _insert("curriculum", {"goal_id": goal_id, "seq": seq, "video_id": video_id,
                           "rationale": rationale, "state": "planned"}, prefer="return=minimal")
    return True


def next_unprocessed(goal_id):
    rows = _req("GET", "/curriculum", params={"select": "*", "goal_id": f"eq.{goal_id}",
                                              "state": "eq.planned", "order": "seq", "limit": 1})
    return rows[0] if rows else None


def mark_curriculum(cid, state):
    _update("curriculum", {"id": cid}, {"state": state})


# ---------- channels ----------
def add_channel(user_id, channel_id):
    rows = _select("monitored_channels", {"user_id": user_id, "channel_id": channel_id}, "id")
    if rows:
        return rows[0]["id"]
    return _insert("monitored_channels", {"user_id": user_id, "channel_id": channel_id})["id"]


def monitored_channels(user_id):
    return _select("monitored_channels", {"user_id": user_id}, "*", order="id")


def mark_channel_checked(cid, last_video_id):
    _update("monitored_channels", {"id": cid}, {"last_video_id": last_video_id, "last_checked": "now()"})


# ---------- runs ----------
def log_run(user_id, job, decided, actions, status):
    return _insert("runs", {"user_id": user_id, "job": job, "decided": decided,
                            "actions": actions, "status": status})


# ---------- curator library ----------
def library_stats():
    rows = _select("concepts", select="video_id,videos(genre)")
    by = {}
    for r in rows:
        g = (r.get("videos") or {}).get("genre") or "unknown"
        by.setdefault(g, set()).add(r["video_id"])
    return [{"genre": g, "videos": len(v), "widgets": 0} for g, v in sorted(by.items(), key=lambda x: len(x[1]))]
