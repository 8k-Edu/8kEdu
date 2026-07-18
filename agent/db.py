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


def ensure_video(video_id, title="", channel_name=""):
    """Curriculum.video_id has an FK to videos — make sure the row exists first."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "insert into videos(video_id,title,channel_name) values (%s,%s,%s) "
            "on conflict (video_id) do update set title=coalesce(nullif(excluded.title,''), videos.title)",
            (video_id, title, channel_name))
        c.commit()


def add_to_curriculum(goal_id, video_id, rationale, title="", channel_name=""):
    ensure_video(video_id, title, channel_name)
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


def add_channel(user_id, channel_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select id from monitored_channels where user_id=%s and channel_id=%s",
                    (user_id, channel_id))
        row = _one(cur)
        if row:
            return row["id"]
        cur.execute("insert into monitored_channels(user_id,channel_id) values (%s,%s) returning id",
                    (user_id, channel_id))
        c.commit()
        return _one(cur)["id"]


def monitored_channels(user_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from monitored_channels where user_id=%s order by id", (user_id,))
        return [dict(r) for r in cur.fetchall()]


def mark_channel_checked(cid, last_video_id):
    with conn() as c, c.cursor() as cur:
        cur.execute("update monitored_channels set last_checked=now(), last_video_id=%s where id=%s",
                    (last_video_id, cid))
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


def dashboard_state(limit=12):
    """Everything the live agent dashboard shows, in one round-trip-ish read."""
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "select id, job, woke_at, status, decided, actions from runs order by woke_at desc limit %s",
            (limit,))
        runs = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "select c.seq, c.video_id, c.rationale, c.state, "
            "coalesce(v.title, c.video_id) as title "
            "from curriculum c left join videos v on v.video_id = c.video_id "
            "order by c.seq")
        curriculum = [dict(r) for r in cur.fetchall()]

        # the moat: concepts cached once, reusable by every learner at ~0 marginal cost
        cur.execute("select count(*) from concepts")
        concepts_cached = cur.fetchone()["count"]
        cur.execute("select count(distinct video_id) from concepts")
        videos_cached = cur.fetchone()["count"]
        # cache reuses = ticks that hit the Supabase cache instead of recomputing
        cur.execute("select count(*) from runs where actions->>'source' = 'supabase-cache'")
        cache_reuses = cur.fetchone()["count"]

        cur.execute("select goal_text from goals where status='active' order by created_at limit 1")
        g = cur.fetchone()
        goal = g["goal_text"] if g else None

        cur.execute("select channel_id, last_checked, last_video_id from monitored_channels order by id")
        channels = [dict(r) for r in cur.fetchall()]

    return {
        "goal": goal,
        "runs": runs,
        "curriculum": curriculum,
        "channels": channels,
        "cache": {
            "concepts_cached": concepts_cached,
            "videos_cached": videos_cached,
            "reuses": cache_reuses,
            # each reuse serves a full video's widgets to another learner for free
            "widgets_served_free": cache_reuses * (concepts_cached // max(1, videos_cached)),
        },
    }
