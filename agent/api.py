"""8kEdu agent dashboard API — read-only Supabase view + a live heartbeat trigger.

Lightweight (no VLM load): powers the /agent dashboard that lets judges SEE the
autonomy — the heartbeat runs feed, the curriculum building itself, the cache moat,
and the containment status.

Run:  uv run --with fastapi --with uvicorn --with psycopg2-binary agent/api.py
      GET  /agent/state       → runs + curriculum + cache stats + containment
      POST /agent/tick        → fire one heartbeat now (for the live demo)
      GET  /agent/containment → policy status from the scoutclaw sandbox
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import db, kg, tools

# Load .env early so AGENT_HANDLE (and everything else) is set before routes fire.
db.load_env()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = Path(__file__).resolve().parent.parent
DOCKER_HOST = "unix:///Users/azehady/.orbstack/run/docker.sock"


def _handle() -> str:
    """Learner identity for this process. Isolates state on a shared Supabase."""
    return os.environ.get("AGENT_HANDLE", "demo")


@app.get("/agent/state")
def state():
    try:
        user_id = db.ensure_learner(_handle())
        return {"ok": True, **db.dashboard_state(user_id)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/agent/tick")
def tick():
    """Fire one heartbeat and return the decision — the agent wakes on demand for the demo."""
    from agent import loop
    try:
        user_id = db.ensure_learner(_handle())
        goal = db.active_goal(user_id)
        if not goal:
            goal = {"id": db.set_goal(user_id, "master transformers from Karpathy's lecture"),
                    "goal_text": "master transformers from Karpathy's lecture"}
        decision = loop.tick(user_id, goal)
        return {"ok": True, "decision": decision}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


_containment_cache = {"data": None}


@app.get("/agent/library")
def library():
    """Cached videos grouped by genre — the live gallery, grown by the curator."""
    try:
        return {"ok": True, "videos": db.library_videos()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "videos": []}


def _pctile(sorted_values, p):
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(round((p / 100.0) * (len(sorted_values) - 1))))
    return sorted_values[idx]


@app.get("/agent/perf")
def perf(limit: int = 50, scope: str = "mine"):
    """Recent widget_events + p50/p90/p99. scope='mine' filters to AGENT_HANDLE; 'all' returns global."""
    try:
        handle = _handle() if scope == "mine" else None
        events = db.recent_widget_events(handle=handle, limit=limit)
        totals = sorted([e["t_total_ms"] for e in events if e.get("t_total_ms") is not None])
        vlms = sorted([e["t_backend_ask_ms"] for e in events
                       if e.get("t_backend_ask_ms") is not None and not e.get("cache_hit")])
        hit_rate = round(sum(1 for e in events if e.get("cache_hit")) / len(events), 3) if events else 0.0
        return {
            "ok": True,
            "handle": handle,
            "count": len(events),
            "events": events,
            "aggregates": {
                "cache_hit_rate": hit_rate,
                "t_total_p50_ms": _pctile(totals, 50),
                "t_total_p90_ms": _pctile(totals, 90),
                "t_total_p99_ms": _pctile(totals, 99),
                "t_backend_ask_p50_ms": _pctile(vlms, 50),
                "t_backend_ask_p90_ms": _pctile(vlms, 90),
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "events": [], "aggregates": {}}


@app.get("/agent/containment")
def containment():
    """Live policy status from the scoutclaw sandbox (cached — the sandbox call is slow)."""
    if _containment_cache["data"] is not None:
        return _containment_cache["data"]
    env = {**os.environ, "DOCKER_HOST": os.environ.get("DOCKER_HOST", DOCKER_HOST),
           "NEMOCLAW_NO_POLICY_HINT": "1"}
    out = {"sandbox": "scoutclaw", "policy": "8kedu", "active": False,
           "allow": ["youtube", "apify", "supabase", "local-inference"], "denied_actions": 0}
    try:
        r = subprocess.run(["nemoclaw", "scoutclaw", "policy-list"],
                           capture_output=True, text=True, timeout=20, env=env)
        out["active"] = "8kedu" in r.stdout and "user-added" in r.stdout
    except Exception as e:
        out["error"] = str(e)[:120]
    try:
        r = subprocess.run(["nemoclaw", "scoutclaw", "logs", "--tail", "150"],
                           capture_output=True, text=True, timeout=20, env=env)
        out["denied_actions"] = r.stdout.count("DENIED")
    except Exception:
        pass
    _containment_cache["data"] = out
    return out


class GraphBuild(BaseModel):
    topic: str = "ai_stem"
    video_ids: list[str] = Field(default_factory=lambda: ["kCc8FmEb1nY"])


class RecursionReplay(BaseModel):
    topic: str = "ai_stem"
    target_video_id: str = "42L1q1Z4Ojc"
    add_to_graph: bool = True


@app.get("/agent/graph")
def graph(topic: str = "ai_stem"):
    try:
        return {"ok": True, **kg.graph_snapshot(topic)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:240], "nodes": [], "edges": [], "summary": {}}


@app.post("/agent/kg/build")
def graph_build(req: GraphBuild):
    try:
        return kg.build_graph(req.topic, req.video_ids)
    except Exception as e:
        return {"ok": False, "error": str(e)[:240]}


@app.get("/agent/recursion")
def recursion(topic: str = "ai_stem", limit: int = 30):
    try:
        return {"ok": True, "topic": topic, "runs": kg.recursion_runs(topic, limit)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:240], "runs": []}


@app.post("/agent/recursion/replay")
def recursion_replay(req: RecursionReplay):
    try:
        return kg.replay_benchmark(req.topic, req.target_video_id, req.add_to_graph)
    except Exception as e:
        return {"ok": False, "error": str(e)[:240]}


# ---------- R1: dynamic curriculum (Duolingo-style) ----------
class Propose(BaseModel):
    subject: str
    kind: str = "subject"   # how-to | concept | subject
    level: str = "beginner"


@app.post("/agent/learn/propose")
def learn_propose(req: Propose):
    """Learner says what to learn → agent finds videos → proposes 2 course paths."""
    try:
        user_id = db.ensure_learner(_handle())
        goal_id = db.set_goal(user_id, req.subject)
        with db.conn() as c, c.cursor() as cur:
            cur.execute("update goals set kind=%s, level=%s where id=%s", (req.kind, req.level, goal_id))
            c.commit()
        vids = tools.find_video(req.subject, 6)
        if not vids:
            return {"ok": False, "error": "no videos found"}
        titles = {v["id"]: v["title"] for v in vids}
        # two real paths from the same search: a fast track and a deep dive
        fast = vids[:3]
        deep = vids[:6]
        p_fast = db.create_path(goal_id, "Fast track",
                                f"The {len(fast)} essential videos to grasp {req.subject} quickly.",
                                [v["id"] for v in fast], len(fast) * 12)
        p_deep = db.create_path(goal_id, "Deep dive",
                                f"A thorough {len(deep)}-video path through {req.subject}, start to mastery.",
                                [v["id"] for v in deep], len(deep) * 15)
        paths = db.paths_for_goal(goal_id)
        for p in paths:
            p["videos"] = [{"id": vid, "title": titles.get(vid, vid)} for vid in p["video_ids"]]
        return {"ok": True, "goal_id": goal_id, "subject": req.subject, "kind": req.kind,
                "paths": paths, "titles": titles}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


class Choose(BaseModel):
    goal_id: int
    path_id: int
    titles: dict = {}


@app.post("/agent/learn/choose")
def learn_choose(req: Choose):
    try:
        n = db.choose_path(req.goal_id, req.path_id, req.titles)
        return {"ok": True, "units": n, **learn_course(req.goal_id)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/agent/learn/course")
def learn_course(goal_id: int):
    with db.conn() as c, c.cursor() as cur:
        import psycopg2.extras
        cur2 = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur2.execute(
            "select c.unit, c.video_id, c.state, coalesce(nullif(c.lesson_title,''), v.title, c.video_id) as title, "
            "(select count(*) from concepts cc where cc.video_id=c.video_id) as widgets "
            "from curriculum c left join videos v on v.video_id=c.video_id "
            "where c.goal_id=%s order by coalesce(c.unit, c.seq)", (goal_id,))
        units = [dict(r) for r in cur2.fetchall()]
    return {"goal_id": goal_id, "units": units}


# ---------- R2: social remix network ----------
class Publish(BaseModel):
    video_id: str
    t_s: float = 0
    widget: str = ""
    title: str = ""
    spec: dict
    owner: str = "demo"


@app.post("/pub/artifact")
def pub_publish(req: Publish):
    try:
        aid = db.publish_artifact(req.owner, req.video_id, req.t_s, req.widget, req.title, req.spec)
        return {"ok": True, "id": aid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/pub/feed")
def pub_feed(sort: str = "hot"):
    try:
        return {"ok": True, "items": db.feed(sort)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "items": []}


class Vote(BaseModel):
    artifact_id: int
    voter: str = "demo"


@app.post("/pub/vote")
def pub_vote(req: Vote):
    try:
        return {"ok": True, "votes": db.vote(req.artifact_id, req.voter)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


class Fork(BaseModel):
    artifact_id: int
    owner: str = "demo"


@app.post("/pub/fork")
def pub_fork(req: Fork):
    try:
        nid = db.fork_artifact(req.artifact_id, req.owner)
        return {"ok": bool(nid), "id": nid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    print(f"agent dashboard API → http://127.0.0.1:{args.port}/agent/state")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
