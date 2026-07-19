"""Supabase (Postgres) access — the agent's persistent memory + shared cache."""
import json
import os
import queue as _queue
import threading as _threading
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


# ---------- inference_cache — frame-level moat: identical asks across users never recompute ----------
def cache_get(prompt_hash):
    """Hit → return the stored result and bump the hits counter. Miss → None."""
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select result from inference_cache where prompt_hash=%s", (prompt_hash,))
        row = _one(cur)
        if not row:
            return None
        cur.execute("update inference_cache set hits = hits + 1 where prompt_hash=%s", (prompt_hash,))
        c.commit()
        return row["result"]


def cache_put(prompt_hash, video_id, model, result):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "insert into inference_cache(cache_key,video_id,model,prompt_hash,result,hits) "
            "values (%s,%s,%s,%s,%s,0) on conflict (cache_key) do nothing",
            (prompt_hash, video_id, model, prompt_hash, json.dumps(result)))
        c.commit()


# ---------- widget_events — per-request observability for the /api/* hot path ----------
_WIDGET_EVENT_KEYS = (
    "handle", "video_id", "t_s", "frame_file", "kind",
    "t_cache_lookup_ms", "t_backend_ask_ms", "t_parse_validate_ms", "t_total_ms",
    "cache_hit", "model", "spec_valid", "widget_kind", "error",
)


def log_widget_event(payload: dict) -> None:
    """Insert one row into widget_events synchronously (opens its own connection).
    Kept for tests / one-off callers. The hot path uses enqueue_widget_event instead."""
    cols = ",".join(_WIDGET_EVENT_KEYS)
    placeholders = ",".join(["%s"] * len(_WIDGET_EVENT_KEYS))
    values = [payload.get(k) for k in _WIDGET_EVENT_KEYS]
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(f"insert into widget_events({cols}) values ({placeholders})", values)
            c.commit()
    except Exception:
        pass  # observability must never break the request


# --- fire-and-forget telemetry writer -------------------------------------------------
# A single background thread drains a bounded queue holding ONE reused connection, so the
# hot path (serve.py /api/*) pays only a microsecond put_nowait — no per-event connect,
# no .env disk read, no unbounded thread spawning. Events are dropped (never blocked) if
# the queue backs up; batched inserts share a commit during bursts; the writer reconnects
# on connection loss (Supabase pooler may drop an idle connection).
_event_q: "_queue.Queue | None" = None
_writer_started = False
_writer_lock = _threading.Lock()
_EVENT_Q_MAX = 1000
_EVENT_BATCH_MAX = 20


def _widget_event_writer() -> None:
    cols = ",".join(_WIDGET_EVENT_KEYS)
    placeholders = ",".join(["%s"] * len(_WIDGET_EVENT_KEYS))
    sql = f"insert into widget_events({cols}) values ({placeholders})"
    c = None
    while True:
        batch = [_event_q.get()]  # block until at least one event
        try:  # opportunistically coalesce a burst into one commit
            while len(batch) < _EVENT_BATCH_MAX:
                batch.append(_event_q.get_nowait())
        except _queue.Empty:
            pass
        rows = [[e.get(k) for k in _WIDGET_EVENT_KEYS] for e in batch]
        for _attempt in (1, 2):  # reconnect-and-retry once on connection loss
            try:
                if c is None or c.closed:
                    c = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=20)
                with c.cursor() as cur:
                    cur.executemany(sql, rows)
                c.commit()
                break
            except Exception:
                try:
                    if c:
                        c.close()
                except Exception:
                    pass
                c = None  # force a fresh connect on retry; drop the batch if retry fails


def enqueue_widget_event(payload: dict) -> None:
    """Non-blocking hand-off to the single writer thread. Drops the event if the queue is
    full — telemetry must never block or OOM the request path."""
    global _event_q, _writer_started
    if not _writer_started:
        with _writer_lock:
            if not _writer_started:
                load_env()  # ensure SUPABASE_DB_URL before the writer's first connect
                _event_q = _queue.Queue(maxsize=_EVENT_Q_MAX)
                _threading.Thread(target=_widget_event_writer, daemon=True,
                                  name="widget-event-writer").start()
                _writer_started = True
    try:
        _event_q.put_nowait(payload)
    except _queue.Full:
        pass


def recent_widget_events(handle: str | None = None, limit: int = 50) -> list[dict]:
    """Most recent widget_events, optionally scoped to a handle."""
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if handle:
            cur.execute(
                "select * from widget_events where handle=%s order by created_at desc limit %s",
                (handle, limit))
        else:
            cur.execute("select * from widget_events order by created_at desc limit %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


# ---------- curator: grow the shared library per genre ----------
def set_video_genre(video_id, genre, title="", channel_name=""):
    ensure_video(video_id, title, channel_name)
    with conn() as c, c.cursor() as cur:
        cur.execute("update videos set genre=%s where video_id=%s", (genre, video_id))
        c.commit()


def is_cached(video_id):
    with conn() as c, c.cursor() as cur:
        cur.execute("select count(*) from concepts where video_id=%s", (video_id,))
        return cur.fetchone()[0] > 0


def library_stats():
    """Per-genre: how many videos are cached, and how many widgets total."""
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "select coalesce(v.genre,'unknown') as genre, "
            "count(distinct co.video_id) as videos, count(*) as widgets "
            "from concepts co left join videos v on v.video_id=co.video_id "
            "group by coalesce(v.genre,'unknown') order by videos")
        return [dict(r) for r in cur.fetchall()]


def library_videos():
    """Every cached video with its genre, title, and widget count — powers the live gallery."""
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "select co.video_id, coalesce(v.genre,'unknown') as genre, "
            "coalesce(v.title, co.video_id) as title, coalesce(v.channel_name,'') as channel, "
            "count(*) as widgets, array_agg(distinct co.widget) as widget_kinds "
            "from concepts co left join videos v on v.video_id=co.video_id "
            "where co.widget is not null and co.widget <> 'none' "
            "group by co.video_id, v.genre, v.title, v.channel_name "
            "order by count(*) desc")
        return [dict(r) for r in cur.fetchall()]


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


# ---------- R2: social remix network — public artifacts + votes ----------
def publish_artifact(owner, video_id, t_s, widget, title, spec, remixed_from=None):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "insert into artifacts_pub(owner,video_id,t_s,widget,title,spec,remixed_from) "
            "values (%s,%s,%s,%s,%s,%s,%s) returning id",
            (owner, video_id, t_s, widget, title, json.dumps(spec), remixed_from))
        c.commit()
        return _one(cur)["id"]


def feed(sort="hot", limit=30):
    order = ("(votes) desc, a.created_at desc" if sort == "hot" else "a.created_at desc")
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"select a.*, (select count(*) from votes v where v.artifact_id=a.id) as votes "
            f"from artifacts_pub a order by {order} limit %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


def vote(artifact_id, voter="demo"):
    with conn() as c, c.cursor() as cur:
        cur.execute("insert into votes(artifact_id,voter) values (%s,%s) on conflict do nothing",
                    (artifact_id, voter))
        c.commit()
        cur.execute("select count(*) from votes where artifact_id=%s", (artifact_id,))
        return cur.fetchone()[0]


def fork_artifact(artifact_id, owner="demo"):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from artifacts_pub where id=%s", (artifact_id,))
        src = _one(cur)
    if not src:
        return None
    spec = src["spec"] if isinstance(src["spec"], dict) else json.loads(src["spec"])
    return publish_artifact(owner, src["video_id"], src["t_s"], src["widget"],
                            f"{src['title']} (remix)", spec, remixed_from=artifact_id)


# ---------- R1: dynamic curriculum — course paths ----------
def create_path(goal_id, label, rationale, video_ids, est_minutes, auto=False):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "insert into paths(goal_id,label,rationale,video_ids,est_minutes,auto) "
            "values (%s,%s,%s,%s,%s,%s) returning id",
            (goal_id, label, rationale, video_ids, est_minutes, auto))
        c.commit()
        return _one(cur)["id"]


def paths_for_goal(goal_id):
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from paths where goal_id=%s order by est_minutes", (goal_id,))
        return [dict(r) for r in cur.fetchall()]


def choose_path(goal_id, path_id, titles=None):
    """Materialize a chosen path into curriculum units (one unit per video)."""
    titles = titles or {}
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select video_ids from paths where id=%s", (path_id,))
        row = _one(cur)
        if not row:
            return 0
        cur.execute("update goals set chosen_path_id=%s where id=%s", (path_id, goal_id))
        cur.execute("delete from curriculum where goal_id=%s", (goal_id,))
        c.commit()
    for i, vid in enumerate(row["video_ids"], 1):
        add_to_curriculum(goal_id, vid, f"unit {i} of the chosen path", title=titles.get(vid, ""))
        with conn() as c, c.cursor() as cur:
            cur.execute("update curriculum set unit=%s, lesson_title=%s where goal_id=%s and video_id=%s",
                        (i, titles.get(vid, f"Unit {i}"), goal_id, vid))
            c.commit()
    return len(row["video_ids"])


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


def dashboard_state(user_id, limit=12):
    """Everything the live agent dashboard shows, in one round-trip-ish read.

    Per-learner state (runs, curriculum, goals, channels) is filtered by user_id
    so teammates sharing this Supabase see only their own workspace. The cache
    stats (concepts_cached / videos_cached / infer_hits / infer_entries) stay
    global — that's the moat, shared by design.
    """
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "select id, job, woke_at, status, decided, actions from runs "
            "where user_id=%s order by woke_at desc limit %s",
            (user_id, limit))
        runs = [dict(r) for r in cur.fetchall()]

        # scope the course to THIS learner's active goal (single-course dashboard view)
        cur.execute(
            "select id from goals where user_id=%s and status='active' "
            "order by created_at limit 1", (user_id,))
        grow = cur.fetchone()
        active_goal_id = grow["id"] if grow else None
        cur.execute(
            "select c.seq, c.video_id, c.rationale, c.state, "
            "coalesce(v.title, c.video_id) as title "
            "from curriculum c left join videos v on v.video_id = c.video_id "
            "where c.goal_id = %s order by c.seq", (active_goal_id,))
        curriculum = [dict(r) for r in cur.fetchall()]

        # the moat: concepts cached once, reusable by every learner at ~0 marginal cost
        cur.execute("select count(*) from concepts")
        concepts_cached = cur.fetchone()["count"]
        cur.execute("select count(distinct video_id) from concepts")
        videos_cached = cur.fetchone()["count"]
        # this learner's cache reuses = their ticks that hit Supabase instead of recomputing
        cur.execute(
            "select count(*) from runs where user_id=%s and actions->>'source' = 'supabase-cache'",
            (user_id,))
        cache_reuses = cur.fetchone()["count"]
        # frame-level cache: identical asks served without a VLM call (global)
        cur.execute("select coalesce(sum(hits),0) as h, count(*) as n from inference_cache")
        ic = cur.fetchone()
        infer_hits, infer_entries = int(ic["h"]), int(ic["n"])

        cur.execute(
            "select goal_text from goals where user_id=%s and status='active' "
            "order by created_at limit 1", (user_id,))
        g = cur.fetchone()
        goal = g["goal_text"] if g else None

        cur.execute(
            "select channel_id, last_checked, last_video_id from monitored_channels "
            "where user_id=%s order by id", (user_id,))
        channels = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "select coalesce(v.genre,'unknown') as genre, count(distinct co.video_id) as videos "
            "from concepts co left join videos v on v.video_id=co.video_id "
            "group by coalesce(v.genre,'unknown') order by videos desc")
        library = [dict(r) for r in cur.fetchall()]

    return {
        "goal": goal,
        "runs": runs,
        "curriculum": curriculum,
        "channels": channels,
        "library": library,
        "cache": {
            "concepts_cached": concepts_cached,
            "videos_cached": videos_cached,
            "reuses": cache_reuses,
            # each reuse serves a full video's widgets to another learner for free
            "widgets_served_free": cache_reuses * (concepts_cached // max(1, videos_cached)),
            # frame-level cache (identical asks across users)
            "infer_hits": infer_hits,
            "infer_entries": infer_entries,
            "hit_rate": round(infer_hits / (infer_hits + infer_entries), 3) if infer_entries else 0.0,
            # a saved VLM call ≈ $0.002 (what the same inference would cost on a cloud VLM)
            "usd_saved": round((cache_reuses * concepts_cached + infer_hits) * 0.002, 2),
        },
    }
