"""Supabase (Postgres) access — the agent's persistent memory + shared cache."""
import json
import os
from pathlib import Path
import psycopg2
import psycopg2.extras


def load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def conn():
    load_env()
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=20)


def _one(cur):
    r = cur.fetchone()
    return dict(r) if r else None


def ensure_learner(handle="demo"):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select user_id from learners where handle=%s", (handle,))
        row = _one(cur)
        if row:
            return row["user_id"]
        cur.execute("insert into learners(handle) values (%s) returning user_id", (handle,))
        c.commit()
        return _one(cur)["user_id"]


def set_goal(user_id, goal_text):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select id from goals where user_id=%s and goal_text=%s and status='active'",
                    (user_id, goal_text))
        row = _one(cur)
        if row:
            return row["id"]
        cur.execute("insert into goals(user_id,goal_text) values (%s,%s) returning id",
                    (user_id, goal_text))
        c.commit()
        return _one(cur)["id"]


def active_goal(user_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from goals where user_id=%s and status='active' order by created_at limit 1",
                    (user_id,))
        return _one(cur)


def curriculum(goal_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from curriculum where goal_id=%s order by seq", (goal_id,))
        return [dict(r) for r in cur.fetchall()]


def add_to_curriculum(goal_id, video_id, rationale):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select 1 from curriculum where goal_id=%s and video_id=%s", (goal_id, video_id))
        if cur.fetchone():
            return False
        cur.execute("select coalesce(max(seq),0)+1 as n from curriculum where goal_id=%s", (goal_id,))
        seq = _one(cur)["n"]
        cur.execute("insert into curriculum(goal_id,seq,video_id,rationale,state) values (%s,%s,%s,%s,'planned')",
                    (goal_id, seq, video_id, rationale))
        c.commit()
        return True


def next_unprocessed(goal_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from curriculum where goal_id=%s and state='planned' order by seq limit 1", (goal_id,))
        return _one(cur)


def mark_curriculum(cid, state):
    with conn() as c, c.cursor() as cur:
        cur.execute("update curriculum set state=%s where id=%s", (state, cid))
        c.commit()


def log_run(user_id, job, decided, actions, status):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "insert into runs(user_id,job,decided,actions,status) values (%s,%s,%s,%s,%s) returning id,woke_at",
            (user_id, job, json.dumps(decided), json.dumps(actions), status))
        c.commit()
        return _one(cur)


def recent_runs(limit=10):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select job,woke_at,status,decided from runs order by woke_at desc limit %s", (limit,))
        return [dict(r) for r in cur.fetchall()]
