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

from agent import db

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = Path(__file__).resolve().parent.parent
DOCKER_HOST = "unix:///Users/azehady/.orbstack/run/docker.sock"


@app.get("/agent/state")
def state():
    try:
        return {"ok": True, **db.dashboard_state()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/agent/tick")
def tick():
    """Fire one heartbeat and return the decision — the agent wakes on demand for the demo."""
    from agent import loop
    try:
        user_id = db.ensure_learner("demo")
        goal = db.active_goal(user_id)
        if not goal:
            goal = {"id": db.set_goal(user_id, "master transformers from Karpathy's lecture"),
                    "goal_text": "master transformers from Karpathy's lecture"}
        decision = loop.tick(user_id, goal)
        return {"ok": True, "decision": decision}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


_containment_cache = {"data": None}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    print(f"agent dashboard API → http://127.0.0.1:{args.port}/agent/state")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
