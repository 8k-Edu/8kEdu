"""Keyframe pixels in Supabase Storage — the durable half of data/<videoId>/frames/.

Those jpgs are a local ffmpeg artifact (gitignored), so before this module a cache miss on
any machine that never ran ingest.py was unrecoverable: serve.py could only answer "this
video's keyframes aren't on disk". Reads use SUPABASE_SECRET_KEY, which authenticates as
service_role and therefore bypasses the private bucket's RLS — the browser never touches
the bucket, and no storage.objects policy exists.

Every env read is lazy. agent/brain.py is the cautionary precedent: it reads os.environ at
import time, before load_env() runs, and under pm2 nothing sources .env — an import-time
KeyError there would be a permanent restart loop.
"""
import os
import threading
import time
from pathlib import Path

DEFAULT_BUCKET = "frames"
_NEG_TTL_S = 60.0
_NEG_MAX = 2048

_client = None
_client_lock = threading.Lock()
_neg: dict[tuple[str, str], float] = {}
_neg_lock = threading.Lock()


def bucket_name() -> str:
    return os.environ.get("KEDU_FRAMES_BUCKET", DEFAULT_BUCKET)


def enabled() -> bool:
    if os.environ.get("KEDU_FRAME_REMOTE", "1") == "0":
        return False
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


def object_key(video_id: str, frame_file: str) -> str:
    """From the filename, never t_s: ingest writes `time` as round(sec, 1) and the filename as
    int(sec), so a t_s-derived key 404s on about a third of frames."""
    return f"{video_id}/{frame_file}"


def _sb():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from supabase import ClientOptions, create_client
                # Not KEDU_TIMEOUT (240s): /api/* are sync defs on a 40-slot threadpool, so
                # hung sockets cascade — see analyze.py's max_retries=0 note.
                timeout = float(os.environ.get("KEDU_FRAME_FETCH_TIMEOUT", "5"))
                _client = create_client(
                    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"],
                    options=ClientOptions(auto_refresh_token=False, persist_session=False,
                                          storage_client_timeout=timeout))
    return _client


def _bucket():
    return _sb().storage.from_(bucket_name())


def _neg_hit(key: tuple[str, str]) -> bool:
    with _neg_lock:
        until = _neg.get(key)
        if until is None:
            return False
        if until > time.monotonic():
            return True
        _neg.pop(key, None)
        return False


def _neg_put(key: tuple[str, str]) -> None:
    with _neg_lock:
        # FIFO: drop the oldest insertion, not the whole map. A burst of misses against
        # an unpublished video would otherwise wipe the cache repeatedly and defeat it.
        while len(_neg) >= _NEG_MAX:
            _neg.pop(next(iter(_neg)))
        _neg[key] = time.monotonic() + _NEG_TTL_S


def fetch_frame(video_id: str, frame_file: str) -> bytes | None:
    """None on anything that isn't a hit. Misses are cached briefly — most videos in the
    library have a manifest but no objects, and they'd otherwise pay a round trip per
    request."""
    if not enabled():
        return None
    key = (video_id, frame_file)
    if _neg_hit(key):
        return None
    try:
        data = _bucket().download(object_key(video_id, frame_file))
    except Exception:
        _neg_put(key)
        return None
    if not data:
        _neg_put(key)
        return None
    return data


def upload_frame(video_id: str, path: Path) -> str:
    """Callers check enabled() first — unlike the read side, a silent no-op here would look
    like a successful publish."""
    key = object_key(video_id, path.name)
    _bucket().upload(key, path.read_bytes(),
                     {"content-type": "image/jpeg", "upsert": "true"})
    with _neg_lock:
        _neg.pop((video_id, path.name), None)
    return key


def ensure_bucket() -> None:
    """Idempotent — the migration creates the bucket, but the backfill has to work on a
    checkout where it hasn't been applied yet."""
    try:
        _sb().storage.create_bucket(
            bucket_name(),
            options={"public": False, "allowed_mime_types": ["image/jpeg"],
                     "file_size_limit": 4194304})
    except Exception as e:
        if "exist" not in str(e).lower():
            raise


def remove_objects(keys: list[str]) -> int:
    if not keys or not enabled():
        return 0
    _bucket().remove(keys)
    with _neg_lock:
        for k in keys:
            vid, _, name = k.partition("/")
            _neg.pop((vid, name), None)
    return len(keys)


def remove_video(video_id: str) -> int:
    """Re-extracting at a different interval renames every frame, and scrub_video.py's
    cold-retest loop drops the local dir — without this both leak a whole video of objects."""
    if not enabled():
        return 0
    return remove_objects([f"{video_id}/{o['name']}" for o in _bucket().list(video_id)])
