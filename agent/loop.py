"""8kEdu autonomous learning agent — heartbeat loop.

Each tick: read state from Supabase → Nemotron decides the next action → (act) → log the run.
Run one tick:   uv run --with openai --with psycopg2-binary agent/loop.py --once --goal "master transformers"
Run forever:    uv run ... agent/loop.py --interval 60
"""
import argparse
import time
from agent import db, brain

DECIDE_SYSTEM = (
    "You are 8kEdu, an autonomous learning agent. On each heartbeat you decide the single next "
    "action that best advances the learner toward their goal. Actions: "
    "FIND_VIDEO (search for a lecture on the weakest uncovered concept), "
    "PROCESS_VIDEO (turn a found video into interactive widgets), "
    "SEQUENCE (order the curriculum), "
    "MONITOR (check watched channels for new uploads), "
    "IDLE (nothing needed this tick). "
    'Return JSON: {"action": <one of above>, "concept": <string or null>, "why": <one sentence>}.'
)


def tick(user_id, goal):
    curr = db.curriculum(goal["id"])
    state = (f'Goal: "{goal["goal_text"]}". Curriculum has {len(curr)} items. '
             f'{"No videos processed yet." if not curr else ""}')
    decision = brain.decide(DECIDE_SYSTEM, state)
    action = decision.get("action", "IDLE")
    # P0: log the autonomous decision. (Tool execution wired in P1.)
    run = db.log_run(user_id, "curriculum", decision, {"planned": action}, "ok")
    print(f"[tick] {run['woke_at']}  decided={action}  why={decision.get('why','')[:80]}")
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
