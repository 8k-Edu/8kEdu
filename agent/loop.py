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


def tick(user_id, goal):
    curr = db.curriculum(goal["id"])
    planned = [c for c in curr if c["state"] == "planned"]
    ready = [c for c in curr if c["state"] == "ready"]
    state = (f'Goal: "{goal["goal_text"]}". Curriculum: {len(curr)} items '
             f'({len(planned)} planned/unprocessed, {len(ready)} processed).')
    decision = brain.decide(DECIDE_SYSTEM, state)
    action = decision.get("action", "IDLE")
    actions = {}

    if action == "FIND_VIDEO":
        q = decision.get("concept") or goal["goal_text"]
        vids = tools.find_video(q, 3)
        added = []
        for v in vids[:1]:  # add the top hit to the course
            if db.add_to_curriculum(goal["id"], v["id"], decision.get("why", "")):
                added.append(v)
        actions = {"query": q, "found": [v["title"][:60] for v in vids], "added": added}
    elif action == "PROCESS_VIDEO":
        nxt = db.next_unprocessed(goal["id"])
        if nxt:
            res = tools.process_video(nxt["video_id"])
            db.mark_curriculum(nxt["id"], "ready")
            actions = res
        else:
            actions = {"note": "nothing planned to process"}
    elif action == "MONITOR":
        actions = {"note": "monitor stub — Apify channel check"}

    run = db.log_run(user_id, "curriculum", decision, actions, "ok")
    print(f"[tick] {str(run['woke_at'])[11:19]}  {action:13} {decision.get('why','')[:70]}")
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
