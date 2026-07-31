# Frame Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A click on a moment whose keyframe exists nowhere recovers that one frame from YouTube in ~7s, publishes it so no machine recovers it again, and returns a real widget.

**Architecture:** `ingest.py` gains a single-frame fetch that reuses the library's exact download+extract recipe. `serve.py`'s shared `_frame_path()` gains a third tier after the Storage miss, so both live handlers get recovery without either handler body changing, and `analyze.py`'s batch loop and the contained image are untouched. Publishing switches from prune-and-replace to a reconcile keyed on `(video_id, t_s)`.

**Tech Stack:** Python 3.12, FastAPI, yt-dlp, ffmpeg, psycopg2, Supabase Storage (`supabase` SDK), React 19 + Vite.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-30-frame-recovery-design.md`.
- Branch `frame-recovery`, off `frames-in-supabase` (PR #12) — `agent/storage.py` comes from there.
- Download selector is `bv*[height<=480]+ba/b[height<=480]/b`, matching `ingest.download()`. Never 720.
- Extract recipe is `-vf "scale=-2:720" -q:v 3`, matching `extract_frames`.
- Frame filenames come from the manifest's `file` field. Never recompute from `t_s`.
- Recovery must never raise into a handler and never turn a miss into a 500.
- No new dependency. No module-scope import of `agent.*` in `analyze.py`.
- Comments follow `CLAUDE.md`: why-only, no restating the code.
- Gates: `PYTHONPATH=. uv run --with pytest pytest tests/ -q`, then `uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"`, then `cd app && npm run build`.
- Baseline to preserve: **32 tests passing**.

---

### Task 1: Single-frame fetch in ingest.py

**Files:**
- Modify: `ingest.py` (add `fetch_one_frame` after `extract_frames`)
- Test: `tests/test_frame_recovery.py` (create)

**Interfaces:**
- Consumes: `YTDLP` (module-level list in `ingest.py`), `run()`.
- Produces: `ingest.fetch_one_frame(vid: str, t_s: float, frame_file: str, frames_dir: Path, timeout: int = 60) -> Path | None` — returns the written jpg path, or `None` on any failure. Never raises.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frame_recovery.py
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ingest


class FetchOneFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.frames = Path(self.tmp.name) / "frames"

    def tearDown(self):
        self.tmp.cleanup()

    def test_uses_the_library_download_selector_and_extract_recipe(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "ffmpeg":
                Path(cmd[-1]).write_bytes(b"\xff\xd8jpeg")
            return 0

        with patch.object(ingest, "run", fake_run):
            out = ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames)

        self.assertEqual(out, self.frames / "f_000210.jpg")
        self.assertEqual(out.read_bytes(), b"\xff\xd8jpeg")
        ytdlp, ffmpeg = calls
        self.assertIn("bv*[height<=480]+ba/b[height<=480]/b", ytdlp)
        self.assertIn("*208.0-215.0", " ".join(ytdlp))
        self.assertIn("--force-keyframes-at-cuts", ytdlp)
        self.assertIn("scale=-2:720", ffmpeg)
        self.assertIn("-q:v", ffmpeg)
        # seek is the lead-in, not the absolute timestamp
        self.assertEqual(ffmpeg[ffmpeg.index("-ss") + 1], "2.0")

    def test_uses_the_manifest_filename_not_the_timestamp(self):
        # ingest writes time=213.0 next to f_000212.jpg for the same frame.
        def fake_run(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                Path(cmd[-1]).write_bytes(b"\xff\xd8jpeg")
            return 0

        with patch.object(ingest, "run", fake_run):
            out = ingest.fetch_one_frame("vid", 213.0, "f_000212.jpg", self.frames)
        self.assertEqual(out.name, "f_000212.jpg")

    def test_early_frame_clamps_the_section_start_at_zero(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "ffmpeg":
                Path(cmd[-1]).write_bytes(b"\xff\xd8jpeg")
            return 0

        with patch.object(ingest, "run", fake_run):
            ingest.fetch_one_frame("vid", 1.0, "f_000001.jpg", self.frames)
        self.assertIn("*0.0-6.0", " ".join(calls[0]))
        self.assertEqual(calls[1][calls[1].index("-ss") + 1], "1.0")

    def test_download_failure_returns_none(self):
        def boom(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        with patch.object(ingest, "run", boom):
            self.assertIsNone(ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames))

    def test_no_frame_written_returns_none(self):
        with patch.object(ingest, "run", lambda cmd, **kw: 0):   # ffmpeg writes nothing
            self.assertIsNone(ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -q`
Expected: FAIL — `AttributeError: module 'ingest' has no attribute 'fetch_one_frame'`

- [ ] **Step 3: Write minimal implementation**

```python
# ingest.py, after extract_frames
FRAME_LEAD_S = 2   # section starts this far before the target so the cut lands cleanly


def fetch_one_frame(vid: str, t_s: float, frame_file: str, frames_dir: Path,
                    timeout: int = 60) -> Path | None:
    """One keyframe straight from YouTube, for a moment whose jpg exists nowhere. Same source
    selector and extract recipe as download()/extract_frames() — a frame at a different
    resolution or quality is one the VLM reads differently from its neighbours.

    frame_file comes from the manifest: `time` is round(sec, 1) but the filename is int(sec),
    so recomputing the name here would miss on about a third of frames."""
    start = max(0.0, t_s - FRAME_LEAD_S)
    seek = t_s - start
    dest = frames_dir / frame_file
    try:
        frames_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / "clip.%(ext)s"
            run(YTDLP + [
                "--download-sections", f"*{start}-{t_s + 5}",
                "--force-keyframes-at-cuts",
                "-f", "bv*[height<=480]+ba/b[height<=480]/b",
                "-o", str(clip),
                f"https://www.youtube.com/watch?v={vid}",
            ], timeout=timeout)
            got = sorted(Path(td).glob("clip.*"))
            if not got:
                return None
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seek), "-i", str(got[0]),
                 "-frames:v", "1", "-vf", f"scale=-2:{FRAME_HEIGHT}", "-q:v", "3", str(dest)],
                timeout=timeout)
        return dest if dest.exists() and dest.stat().st_size else None
    except Exception as e:
        print(f"! frame recovery failed for {vid}@{t_s}: {e}")
        return None
```

Also add `import tempfile` to the import block, and give `run()` a `timeout` passthrough:

```python
def run(cmd: list[str], check: bool = True, timeout: int | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, timeout=timeout).returncode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -q`
Expected: PASS, 5 tests

- [ ] **Step 5: Full gates + commit**

```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -q          # expect 37 passed
uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"
git add ingest.py tests/test_frame_recovery.py
git commit -m "feat: fetch a single keyframe from YouTube on demand"
```

---

### Task 2: Reconcile publish instead of prune-and-replace

**Files:**
- Modify: `agent/db.py` (add `frames_rows`), `agent/storage.py` (add `remove_objects`), `ingest.py` (`upload_frames`), `scripts/backfill_frames.py` (drop the now-wrong comment)
- Test: `tests/test_frame_recovery.py` (append)

**Interfaces:**
- Consumes: `agent.db.upsert_frames`, `agent.storage.upload_frame`, `agent.storage.enabled`.
- Produces: `agent.db.frames_rows(video_id) -> dict[float, str]` mapping `t_s` → `storage_path`; `agent.storage.remove_objects(keys: list[str]) -> int`; `ingest.upload_frames(vid, out, frames, on_upload=None) -> int` — the `prune` parameter is **removed**, reconcile is unconditional.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_frame_recovery.py
class FakeStorageModule:
    def __init__(self):
        self.uploaded, self.removed = [], []

    def enabled(self):
        return True

    def ensure_bucket(self):
        pass

    def upload_frame(self, vid, path):
        self.uploaded.append(path.name)
        return f"{vid}/{path.name}"

    def remove_objects(self, keys):
        self.removed.extend(keys)
        return len(keys)


class FakeDbModule:
    def __init__(self, existing):
        self.existing, self.upserted, self.deleted = existing, [], []

    def load_env(self):
        pass

    def frames_rows(self, vid):
        return dict(self.existing)

    def upsert_frames(self, vid, rows, title=""):
        self.upserted.extend(rows)
        return len(rows)

    def delete_frames_at(self, vid, t_values):
        self.deleted.extend(t_values)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        (self.out / "frames").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, *names):
        for n in names:
            (self.out / "frames" / n).write_bytes(b"\xff\xd8jpeg")

    def _run(self, frames, existing):
        storage, db = FakeStorageModule(), FakeDbModule(existing)
        import agent
        with patch.object(agent, "storage", storage), patch.object(agent, "db", db):
            n = ingest.upload_frames("vid", self.out, frames)
        return n, storage, db

    def test_already_published_frames_are_skipped(self):
        self._write("f_000000.jpg", "f_000030.jpg")
        frames = [{"time": 0.0, "file": "f_000000.jpg"}, {"time": 30.4, "file": "f_000030.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg", 30.4: "vid/f_000030.jpg"})
        self.assertEqual(storage.uploaded, [])
        self.assertEqual(storage.removed, [])
        self.assertEqual(n, 0)

    def test_new_frames_upload_and_upsert(self):
        self._write("f_000000.jpg", "f_000030.jpg")
        frames = [{"time": 0.0, "file": "f_000000.jpg"}, {"time": 30.4, "file": "f_000030.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg"})
        self.assertEqual(storage.uploaded, ["f_000030.jpg"])
        self.assertEqual(db.upserted, [(30.4, "vid/f_000030.jpg")])
        self.assertEqual(n, 1)

    def test_renamed_frame_uploads_and_drops_the_old_object(self):
        self._write("f_000031.jpg")
        frames = [{"time": 31.0, "file": "f_000031.jpg"}]
        n, storage, db = self._run(frames, {31.0: "vid/f_000030.jpg"})
        self.assertEqual(storage.uploaded, ["f_000031.jpg"])
        self.assertEqual(storage.removed, ["vid/f_000030.jpg"])

    def test_orphaned_timestamps_are_deleted_not_the_survivors(self):
        self._write("f_000000.jpg")
        frames = [{"time": 0.0, "file": "f_000000.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg", 999.0: "vid/f_000999.jpg"})
        self.assertEqual(storage.removed, ["vid/f_000999.jpg"])
        self.assertEqual(db.deleted, [999.0])
        self.assertEqual(storage.uploaded, [])   # the survivor is untouched

    def test_a_recovered_frame_absent_from_disk_is_left_published(self):
        # recovery put it in the bucket; a later re-extract at the same interval rewrote
        # local disk, but if the jpg is missing locally we must not delete the published one.
        frames = [{"time": 0.0, "file": "f_000000.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg"})
        self.assertEqual(storage.removed, [])
        self.assertEqual(db.deleted, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -k Reconcile -q`
Expected: FAIL — `AttributeError` on `frames_rows` / `remove_objects` / unexpected `prune`

- [ ] **Step 3: Write minimal implementation**

```python
# agent/db.py, next to frames_manifest
def frames_rows(video_id):
    """t_s → storage_path for everything already published, so a reprocess can skip what it
    already has instead of dropping and re-uploading the lot."""
    with conn() as c, c.cursor() as cur:
        cur.execute("select t_s, storage_path from frames where video_id=%s", (video_id,))
        return {float(t_s): path for t_s, path in cur.fetchall()}


def delete_frames_at(video_id, t_values):
    if not t_values:
        return 0
    with conn() as c, c.cursor() as cur:
        cur.execute("delete from frames where video_id=%s and t_s = any(%s)",
                    (video_id, list(t_values)))
        c.commit()
        return cur.rowcount
```

```python
# agent/storage.py, next to remove_video
def remove_objects(keys: list[str]) -> int:
    if not keys or not enabled():
        return 0
    _bucket().remove(keys)
    with _neg_lock:
        for k in keys:
            vid, _, name = k.partition("/")
            _neg.pop((vid, name), None)
    return len(keys)
```

```python
# ingest.py — replace upload_frames wholesale
def upload_frames(vid: str, out: Path, frames: list[dict], on_upload=None) -> int:
    """Publish `frames` to Supabase Storage and public.frames, uploading only what isn't
    already there. Returns the number uploaded. Raises — callers decide what's fatal.

    Reconciled on (video_id, t_s), the frames primary key, rather than dropping the video's
    objects first: a frame recovered on demand has already been analyzed under its filename,
    and re-uploading identical bytes buys nothing. A re-extract at a different interval
    renames everything, and those genuinely orphaned keys are deleted below."""
    from agent import db, storage
    db.load_env()  # `uv run ingest.py <url>` sources no .env of its own
    if not storage.enabled():
        return 0
    storage.ensure_bucket()

    published = db.frames_rows(vid)
    wanted = {fr["time"]: fr["file"] for fr in frames}

    rows, stale = [], []
    for t_s, name in wanted.items():
        key = f"{vid}/{name}"
        if published.get(t_s) == key:
            continue
        jpg = out / "frames" / name
        if not jpg.exists():
            continue
        if t_s in published:
            stale.append(published[t_s])
        rows.append((t_s, storage.upload_frame(vid, jpg)))
        if on_upload:
            on_upload()

    orphans = [key for t_s, key in published.items() if t_s not in wanted]
    storage.remove_objects(stale + orphans)
    db.delete_frames_at(vid, [t_s for t_s in published if t_s not in wanted])
    db.upsert_frames(vid, rows)
    return len(rows)
```

```python
# ingest.py — publish_frames loses the prune argument
        return upload_frames(vid, out, frames)
```

```python
# scripts/backfill_frames.py — the comment now describes the wrong mechanism
        n = ingest.upload_frames(vid, DATA / vid, frames, on_upload=tick)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Verify against the live bucket — a no-op reprocess must upload nothing**

```bash
uv run python -c "
import json; from pathlib import Path; import ingest
out = Path('data/9C_XcD-WCTM')
frames = json.loads((out/'frames.json').read_text())
print('uploaded:', ingest.upload_frames('9C_XcD-WCTM', out, frames))
"
```
Expected: `uploaded: 0` — all three frames are already published. Then confirm the row count is still 713:
```bash
uv run python -c "
from agent import db; db.load_env()
with db.conn() as c, c.cursor() as cur:
    cur.execute('select count(*) from frames'); print(cur.fetchone()[0])"
```

- [ ] **Step 6: Commit**

```bash
git add agent/db.py agent/storage.py ingest.py scripts/backfill_frames.py tests/test_frame_recovery.py
git commit -m "feat: reconcile published frames on (video_id, t_s) instead of pruning"
```

---

### Task 3: Wire recovery into the live handlers

**Files:**
- Modify: `serve.py` (`_frame_path`, new `_recover_frame`)
- Test: `tests/test_frame_recovery.py` (append)

**Interfaces:**
- Consumes: `ingest.fetch_one_frame`, `agent.storage.upload_frame`, `agent.db.upsert_frames`, `analyze.resolve_frame`.
- Produces: `serve._recover_frame(video: str, fr: dict, src: Path) -> tuple[Path, str, int]` returning `(path, "recovered"|"miss"|"off", elapsed_ms)`; `_frame_path` unchanged in signature.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_frame_recovery.py
import serve


class RecoverFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.absent = Path(self.tmp.name) / "frames" / "f_000210.jpg"
        serve._recovering.clear()

    def tearDown(self):
        self.tmp.cleanup()
        serve._recovering.clear()

    def _fr(self):
        return {"time": 210.0, "file": "f_000210.jpg"}

    def test_recovers_uploads_and_records(self):
        fetched = Path(self.tmp.name) / "frames" / "f_000210.jpg"
        fetched.parent.mkdir(parents=True, exist_ok=True)
        fetched.write_bytes(b"\xff\xd8jpeg")
        uploads, rows = [], []

        with patch.dict(os.environ, {"KEDU_RECOVER_FRAMES": "1"}), \
                patch.object(serve, "_fetch_one_frame", lambda *a, **k: fetched), \
                patch.object(serve, "_publish_recovered", lambda v, t, p: (uploads.append(p), rows.append(t))):
            path, source, ms = serve._recover_frame("vid", self._fr(), self.absent)

        self.assertEqual((path, source), (fetched, "recovered"))
        self.assertEqual(rows, [210.0])
        self.assertGreaterEqual(ms, 0)

    def test_failure_returns_the_original_absent_path(self):
        with patch.dict(os.environ, {"KEDU_RECOVER_FRAMES": "1"}), \
                patch.object(serve, "_fetch_one_frame", lambda *a, **k: None):
            path, source, _ms = serve._recover_frame("vid", self._fr(), self.absent)
        self.assertEqual((path, source), (self.absent, "miss"))

    def test_a_raising_fetch_does_not_escape(self):
        def boom(*a, **k):
            raise RuntimeError("yt-dlp exploded")

        with patch.dict(os.environ, {"KEDU_RECOVER_FRAMES": "1"}), \
                patch.object(serve, "_fetch_one_frame", boom):
            path, source, _ms = serve._recover_frame("vid", self._fr(), self.absent)
        self.assertEqual((path, source), (self.absent, "miss"))

    def test_kill_switch_skips_the_download_entirely(self):
        called = []
        with patch.dict(os.environ, {"KEDU_RECOVER_FRAMES": "0"}), \
                patch.object(serve, "_fetch_one_frame", lambda *a, **k: called.append(1)):
            path, source, ms = serve._recover_frame("vid", self._fr(), self.absent)
        self.assertEqual((path, source, ms), (self.absent, "off", 0))
        self.assertEqual(called, [])

    def test_concurrent_asks_for_one_frame_download_once(self):
        import threading
        fetched = Path(self.tmp.name) / "frames" / "f_000210.jpg"
        fetched.parent.mkdir(parents=True, exist_ok=True)
        fetched.write_bytes(b"\xff\xd8jpeg")
        calls, gate = [], threading.Event()

        def slow(*a, **k):
            calls.append(1)
            gate.wait(2)
            return fetched

        with patch.dict(os.environ, {"KEDU_RECOVER_FRAMES": "1"}), \
                patch.object(serve, "_fetch_one_frame", slow), \
                patch.object(serve, "_publish_recovered", lambda *a: None):
            threads = [threading.Thread(target=serve._recover_frame,
                                        args=("vid", self._fr(), self.absent)) for _ in range(3)]
            for t in threads:
                t.start()
            gate.set()
            for t in threads:
                t.join(5)

        self.assertEqual(len(calls), 1)


class FramePathTests(unittest.TestCase):
    def test_a_storage_miss_escalates_to_recovery_and_sums_the_timings(self):
        ev = {}
        absent = Path("/nonexistent/frames/f_000210.jpg")
        with patch.object(serve, "resolve_frame", return_value=(absent, "miss", 40)), \
                patch.object(serve, "_recover_frame", return_value=(absent, "recovered", 7000)):
            serve._frame_path(ev, "vid", {"time": 210.0, "file": "f_000210.jpg"})
        self.assertEqual(ev["frame_source"], "recovered")
        self.assertEqual(ev["t_frame_fetch_ms"], 7040)

    def test_a_local_hit_never_attempts_recovery(self):
        ev, called = {}, []
        with patch.object(serve, "resolve_frame", return_value=(Path("x.jpg"), "local", 0)), \
                patch.object(serve, "_recover_frame", lambda *a: called.append(1)):
            serve._frame_path(ev, "vid", {"time": 1.0, "file": "x.jpg"})
        self.assertEqual(called, [])
        self.assertEqual(ev["frame_source"], "local")
```

Add `import os` to the test file's imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -k "Recover or FramePath" -q`
Expected: FAIL — `AttributeError: module 'serve' has no attribute '_recovering'`

- [ ] **Step 3: Write minimal implementation**

```python
# serve.py, above _frame_path
_recovering: dict[tuple[str, str], threading.Lock] = {}
_recovering_lock = threading.Lock()


def _fetch_one_frame(video: str, t_s: float, frame_file: str, frames_dir: Path) -> Path | None:
    """Imported lazily: analyze.py must stay importable in the contained image, and ingest
    pulls in yt-dlp machinery the live path only needs on this branch."""
    from ingest import fetch_one_frame
    return fetch_one_frame(video, t_s, frame_file, frames_dir,
                           timeout=int(os.environ.get("KEDU_RECOVER_TIMEOUT", "60")))


def _publish_recovered(video: str, t_s: float, path: Path) -> None:
    """So the next machine reads it out of the bucket instead of downloading it again."""
    from agent import db, storage
    if storage.enabled():
        db.upsert_frames(video, [(t_s, storage.upload_frame(video, path))])


def _recover_frame(video: str, fr: dict, src: Path) -> tuple[Path, str, int]:
    """Last resort for a frame that is on no disk and in no bucket: pull the one moment
    straight from YouTube. Never raises — on any failure it returns `src` untouched so the
    caller's existing not-on-disk handling fires.

    Single-flighted per (video, frame): a learner scrubbing one moment must not spawn a
    yt-dlp per click."""
    if os.environ.get("KEDU_RECOVER_FRAMES", "1") == "0":
        return src, "off", 0
    key = (video, fr["file"])
    with _recovering_lock:
        lock = _recovering.setdefault(key, threading.Lock())
    t0 = time.perf_counter()
    with lock:
        if src.exists():  # another thread just recovered it
            return src, "recovered", _ms(t0)
        try:
            got = _fetch_one_frame(video, fr["time"], fr["file"], src.parent)
            if got is None:
                return src, "miss", _ms(t0)
            _publish_recovered(video, fr["time"], got)
            return got, "recovered", _ms(t0)
        except Exception:
            return src, "miss", _ms(t0)
```

```python
# serve.py — _frame_path gains the third tier
def _frame_path(ev: dict, video: str, fr: dict) -> Path:
    """Local jpg, else Supabase Storage, else pulled from YouTube one frame at a time.
    Only reached on a cache miss, so a cached widget never triggers a download."""
    src, frame_source, t_fetch = resolve_frame(DATA / video / "frames" / fr["file"], video)
    if frame_source == "miss":
        src, frame_source, t_recover = _recover_frame(video, fr, src)
        t_fetch += t_recover
    ev.update(frame_source=frame_source, t_frame_fetch_ms=t_fetch)
    return src
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -q`
Expected: PASS, 17 tests

- [ ] **Step 5: Full gates + commit**

```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -q          # expect 49 passed
uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"
git add serve.py tests/test_frame_recovery.py
git commit -m "feat: recover a missing keyframe from YouTube on a live ask"
```

---

### Task 4: Fix the reprocess gate and surface the recover rate

**Files:**
- Modify: `serve.py` (the `_run_ingest` gate), `agent/api.py` (`/agent/perf`)
- Test: `tests/test_frame_recovery.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `/agent/perf` `aggregates.frame_recover_rate`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_frame_recovery.py
class ReprocessGateTests(unittest.TestCase):
    """serve.py gated the download on the manifest being absent, so reprocessing a video with
    a committed frames.json and no jpgs skipped straight to a doomed analyze pass."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vd = Path(self.tmp.name) / "vid"
        (self.vd / "frames").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manifest_with_no_jpgs_needs_a_download(self):
        (self.vd / "frames.json").write_text("[]")
        self.assertTrue(serve._needs_download(self.vd))

    def test_manifest_with_jpgs_does_not(self):
        (self.vd / "frames.json").write_text("[]")
        (self.vd / "frames" / "f_000000.jpg").write_bytes(b"\xff\xd8")
        self.assertFalse(serve._needs_download(self.vd))

    def test_no_manifest_at_all_needs_a_download(self):
        self.assertTrue(serve._needs_download(self.vd))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/test_frame_recovery.py -k ReprocessGate -q`
Expected: FAIL — `AttributeError: module 'serve' has no attribute '_needs_download'`

- [ ] **Step 3: Write minimal implementation**

```python
# serve.py, above _run_ingest
def _needs_download(vd: Path) -> bool:
    """A committed frames.json with no jpgs beside it still needs the video: analyze.py would
    otherwise error on every frame and SystemExit into the job as a bare failure."""
    return not (vd / "frames.json").exists() or not any((vd / "frames").glob("*.jpg"))
```

```python
# serve.py — inside _run_ingest, replacing the old condition
        if _needs_download(vd):
            _set_job(vid, step="downloading video + transcript + keyframes")
            subprocess.run([py, "ingest.py", url], cwd=ROOT, check=True, timeout=900, env=env)
```

```python
# agent/api.py — inside perf(), beside frame_miss_rate
                "frame_recover_rate": rate("recovered"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run --with pytest pytest tests/ -q`
Expected: PASS, 52 tests

- [ ] **Step 5: Confirm the endpoint reports the new field**

```bash
./run.sh >/dev/null 2>&1; sleep 8
curl -s 'http://127.0.0.1:8787/agent/perf?scope=all&limit=5' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['aggregates'])"
```
Expected: a dict containing `frame_recover_rate`.

- [ ] **Step 6: Commit**

```bash
git add serve.py agent/api.py tests/test_frame_recovery.py
git commit -m "fix: reprocess re-downloads when the manifest has no frames beside it"
```

---

### Task 5: Put the process button on the video view

**Files:**
- Modify: `app/src/App.jsx` (the `{!analyzed && (...)}` block and the video header)

**Interfaces:** none — reuses `processVideo` and `proc` state already in the component.

- [ ] **Step 1: Read the current block**

Run: `grep -n 'analyzed &&' app/src/App.jsx` and read the surrounding 25 lines. The ⚡ panel is
wrapped in `{!analyzed && (...)}`, which is why an analyzed video offers no way to reprocess.

- [ ] **Step 2: Keep the explanatory card for unanalyzed videos, and add a header control for the rest**

Leave the existing `{!analyzed && (...)}` card exactly as it is — it carries the "this video
isn't analyzed yet" copy and the spinner, which are right for a first run. Add beside it:

```jsx
{analyzed && (
  proc?.state === 'running' ? (
    <span style={{ color: '#58a6ff', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span className="kedu-spin" style={{ width: 12, height: 12, border: '2px solid #58a6ff55', borderTopColor: '#58a6ff', borderRadius: '50%', display: 'inline-block' }} />
      {proc.step || 'starting'}…
    </span>
  ) : (
    <button onClick={processVideo} title="Re-download this lecture's keyframes and regenerate its widgets"
      style={{ background: 'transparent', color: '#8b949e', border: '1px solid #30363d', borderRadius: 8, padding: '6px 12px', fontSize: 12, cursor: 'pointer' }}>
      ⚡ Reprocess
    </button>
  )
)}
```

Place it in the same header row as the existing engine/backend controls so it is reachable
without leaving the video.

- [ ] **Step 3: Build and eyeball it**

```bash
cd app && npm run build
```
Expected: `✓ built`. Then load `http://dev.localhost:5174/?v=_yhQg5gFTtQ` and confirm a
**⚡ Reprocess** control is present on a video that already has widgets.

- [ ] **Step 4: Commit**

```bash
git add app/src/App.jsx
git commit -m "feat: offer reprocess from the video view, not just before first analysis"
```

---

### Task 6: End-to-end verification

**Files:** none — verification only.

- [ ] **Step 1: Recover a real frame through the live API**

`_yhQg5gFTtQ` has a committed manifest, no local jpgs and no objects — the exact case that
dead-ended.

```bash
./run.sh >/dev/null 2>&1; sleep 8
time curl -s -m 300 -X POST http://127.0.0.1:8756/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"_yhQg5gFTtQ","time":210,"text":"what makes a rental property cash flow","ask":"recovery e2e 1"}'
```
Expected: a spec or answer card, **not** the keyframes error. Roughly 7s of recovery plus the
model call.

- [ ] **Step 2: Confirm it published, so it never recovers again**

```bash
ls -l data/_yhQg5gFTtQ/frames/
uv run python -c "
from agent import db, storage; db.load_env()
print('rows:', db.frames_manifest('_yhQg5gFTtQ'))
print('objects:', len(storage._bucket().list('_yhQg5gFTtQ')))"
```
Expected: one jpg on disk, one row, one object.

- [ ] **Step 3: Confirm the second ask is a local hit**

```bash
curl -s -m 120 -X POST http://127.0.0.1:8756/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"_yhQg5gFTtQ","time":210,"text":"what makes a rental property cash flow","ask":"recovery e2e 2"}' >/dev/null
curl -s 'http://127.0.0.1:8787/agent/perf?scope=all&limit=3' | python3 -m json.tool | head -30
```
Expected: the newest events show `frame_source` `"recovered"` then `"local"`, and
`frame_recover_rate` is non-zero.

- [ ] **Step 4: Confirm the kill switch**

```bash
KEDU_RECOVER_FRAMES=0 uv run serve.py --backend vllm --port 8758 >/dev/null 2>&1 &
sleep 8
curl -s -m 60 -X POST http://127.0.0.1:8758/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"kCc8FmEb1nY","time":1200,"text":"attention","ask":"killswitch 1"}'
pkill -f "port 8758"
```
Expected: today's keyframes error, no download attempted.

- [ ] **Step 5: Confirm the contained path is still importable without agent/ or yt-dlp**

```bash
R=$PWD; T=$(mktemp -d); cp analyze.py "$T/"
(cd "$T" && "$R/.venv/bin/python" -c "
import sys; sys.path=[p for p in sys.path if 'Personal/8kedu' not in p]; sys.path.insert(0,'.')
import analyze; from pathlib import Path
print(analyze.resolve_frame(Path('data/v/frames/f_0.jpg'),'v'))"); rm -rf "$T"
```
Expected: `(PosixPath('data/v/frames/f_0.jpg'), 'off', 0)` — recovery lives in `serve.py`, so
`analyze.py` standalone is unchanged.

- [ ] **Step 6: Final gates and push**

```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -q
uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"
cd app && npm run build && cd ..
git push -u origin frame-recovery
```
