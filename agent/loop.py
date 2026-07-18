"""8kEdu autonomous learning agent — heartbeat loop.

Each tick: read state from Supabase → Nemotron decides the next action → (act) → log the run.
Run one tick:   uv run --with openai --with psycopg2-binary agent/loop.py --once --goal "master transformers"
Run forever:    uv run ... agent/loop.py --interval 60
"""
import argparse
import time
from agent import db, brain, tools

DECIDE_SYSTEM = (
    "You are 8kEdu, an autonomous learning agent. On each heartbeat you decide the single next "
    "action that best advances the learner toward their goal. Actions: "
    "FIND_VIDEO (search for a lecture — set 'concept' to a good YouTube query), "
    "PROCESS_VIDEO (turn the next planned video into interactive widgets), "
    "SEQUENCE (the planned videos are enough; stop finding), "
    "MONITOR (check watched channels for new uploads), "
    "IDLE (nothing needed). "
    "Prefer FIND_VIDEO when the curriculum has no planned videos; PROCESS_VIDEO when planned videos "
    "await processing. "
    'Return JSON: {"action": <one of above>, "concept": <query string or null>, "why": <one sentence>}.'
)


def heuristic_decision(planned, ready, channels):
    """Fallback when the model is unreachable/garbled — keep the agent moving, never crash."""
    if planned:
        return {"action": "PROCESS_VIDEO", "concept": None, "why": "planned video awaits processing (fallback)"}
    if not (planned or ready):
        return {"action": "FIND_VIDEO", "concept": None, "why": "curriculum empty — find a lecture (fallback)"}
    if channels:
        return {"action": "MONITOR", "concept": None, "why": "course seeded — watch channels (fallback)"}
    return {"action": "IDLE", "concept": None, "why": "nothing to do (fallback)"}


def _act(action, decision, user_id, goal):
    """Execute one action. Raises on tool failure — caller records the error run."""
    if action == "FIND_VIDEO":
        q = decision.get("concept") or goal["goal_text"]
        vids = tools.find_video(q, 3)
        added = []
        for v in vids[:1]:  # add the top hit to the course
            if db.add_to_curriculum(goal["id"], v["id"], decision.get("why", ""), title=v.get("title", "")):
                added.append(v)
        return {"query": q, "found": [v["title"][:60] for v in vids], "added": added}
    if action == "PROCESS_VIDEO":
        nxt = db.next_unprocessed(goal["id"])
        if not nxt:
            return {"note": "nothing planned to process"}
        res = tools.process_video(nxt["video_id"])
        db.mark_curriculum(nxt["id"], "ready")
        return res
    if action == "MONITOR":
        checked, new_uploads = [], []
        for ch in db.monitored_channels(user_id):
            try:
                res = tools.monitor_channel(ch["channel_id"], 3)
                vids = res.get("videos", [])
                newest = vids[0]["id"] if vids else None
                fresh = [] if ch["last_video_id"] is None else [v for v in vids if v["id"] != ch["last_video_id"]]
                for v in fresh:  # add_to_curriculum dedupes (goal_id, video_id)
                    if db.add_to_curriculum(goal["id"], v["id"], f'new upload on {ch["channel_id"]}', title=v.get("title", "")):
                        new_uploads.append({"channel": ch["channel_id"], **v})
                if newest:
                    db.mark_channel_checked(ch["id"], newest)
                checked.append({"channel": ch["channel_id"], "source": res.get("source", "?"),
                                "seen": len(vids), "new": len(new_uploads)})
            except Exception as e:  # one bad channel must not sink the whole MONITOR tick
                checked.append({"channel": ch["channel_id"], "error": str(e)[:100]})
        return {"channels_checked": checked, "new_uploads": new_uploads}
    return {"note": f"no-op for {action}"}


def tick(user_id, goal):
    """One heartbeat. Resilient: model failure → heuristic; tool failure → logged error run; never crashes."""
    curr = db.curriculum(goal["id"])
    planned = [c for c in curr if c["state"] == "planned"]
    ready = [c for c in curr if c["state"] == "ready"]
    channels = db.monitored_channels(user_id)
    state = (f'Goal: "{goal["goal_text"]}". Curriculum: {len(curr)} items '
             f'({len(planned)} planned/unprocessed, {len(ready)} processed). '
             f'Monitored channels: {len(channels)}. '
             f'If planned videos await, PROCESS_VIDEO. If none planned and the course is thin, FIND_VIDEO. '
             f'If the course looks complete and channels are monitored, MONITOR for new uploads.')
    try:
        decision = brain.decide(DECIDE_SYSTEM, state)
        if not isinstance(decision, dict) or "action" not in decision:
            raise ValueError("model returned no action")
    except Exception as e:
        decision = heuristic_decision(planned, ready, channels)
        decision["fallback_reason"] = str(e)[:100]
    action = decision.get("action", "IDLE")

    status, actions = "ok", {}
    try:
        actions = _act(action, decision, user_id, goal)
    except Exception as e:
        status, actions = "error", {"error": str(e)[:160], "action": action}

    try:
        run = db.log_run(user_id, "curriculum", decision, actions, status)
        stamp = str(run["woke_at"])[11:19]
    except Exception as e:  # even a DB hiccup shouldn't crash the heartbeat
        stamp = "--:--:--"
        print("[tick] log_run failed:", str(e)[:100])
    print(f"[tick] {stamp}  {action:13} [{status}] {decision.get('why', '')[:60]}")
    if actions:
        print(f"        → {str(actions)[:110]}")
    return decision


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default="master transformers from Karpathy's lecture")
    ap.add_argument("--handle", default="demo")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    user_id = db.ensure_learner(args.handle)
    goal = db.active_goal(user_id) or {"id": db.set_goal(user_id, args.goal), "goal_text": args.goal}
    print(f"agent up · learner={args.handle} · goal={goal['goal_text']!r}")

    if args.once:
        tick(user_id, goal)
        return
    while True:
        try:
            tick(user_id, goal)
        except Exception as e:
            print("[tick] error:", str(e)[:120])
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
