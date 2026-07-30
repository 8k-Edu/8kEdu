# Testing durable keyframes + on-demand recovery

Covers two stacked branches:

| branch | what it added |
|---|---|
| `frames-in-supabase` (PR #12) | keyframes published to a private Supabase Storage bucket; `serve.py` pulls one back on a local miss; `frames_for()` falls back to `public.frames` |
| `frame-recovery` (on top) | when the bucket has nothing either, pull that one frame from YouTube (~7s); reconcile publishing on `(video_id, t_s)`; reprocess gate fix; header **⚡ Reprocess** button |

Read [three gotchas](#three-gotchas-that-look-like-bugs) before filing anything.

## 0. Bring the stack up

```bash
cd ~/Developer/Personal/8kedu
git checkout frame-recovery

./scripts/serve-vllm-metal.sh          # vision :8000 + brain :8001, ~70s cold
./run.sh                               # serve.py :8756, agent API :8787, vite
```

### The frontend port depends on the branch name — read this first

`app/vite.config.js:10-12` picks the port from the current branch: **`dev` → `dev.localhost:5174`,
anything else → `localhost:5173`.** On `frame-recovery` the app is at **<http://localhost:5173>**.
Set this once and paste it into the commands below:

```bash
export APP=http://localhost:5173      # on branch `dev`: http://dev.localhost:5174
```

`scripts/preflight.sh:17` hardcodes 5174, so on any branch but `dev` it reports the frontend and
all five proxied-data lines as ✗ — **6 spurious failures**, plus 3 that predate this work (the
`:8000` check greps `/v1/models` for `Nemotron` while vllm-metal serves `qwen3-vl-4b`;
`OPENROUTER_API_KEY` isn't in `.env`; the curator only runs under `./run.sh --loop`). Rather than
reading preflight on a feature branch, check the same surface directly:

```bash
for p in "" "EwVfILFo1wQ/concepts.json" "pyodide-dist/pyodide-lock.json" "agent/state" "api/billing"; do
  printf '%-40s %s\n' "/$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$APP/$p")"
done
```

All five must be `200`. (Preflight is worth running on `dev`, where it should show 9 ✓ / 3 ✗.)

`./run.sh` restarts `serve.py`, so run it after any Python change — the recovery code lives in
`serve.py` and a stale process will happily serve the old behaviour.

## 1. Recovery works — the case that used to dead-end

`4Bdc55j80l8` ("Illustrated Guide to Transformers", 901s, 90 frames) has a committed
`frames.json`, **zero local jpgs and zero objects**. Before this work, asking for a widget here
returned *"this video's keyframes aren't on disk"*.

```bash
time curl -s -X POST http://127.0.0.1:8756/api/widget \
  -H 'Content-Type: application/json' \
  -d '{"video":"4Bdc55j80l8","time":450,
       "text":"the encoder self-attention block and how Q K V are formed",
       "ask":"UNIQUE-1"}'
```

**Expect:** a JSON spec (or an answer card — see gotcha 2), roughly 10-15s. **Not** an `error`
field mentioning keyframes.

Then confirm it landed everywhere it should:

```bash
ls -l data/4Bdc55j80l8/frames/
uv run python -c "
from agent import db, storage; db.load_env()
print('rows   :', db.frames_manifest('4Bdc55j80l8'))
print('objects:', [o['name'] for o in storage._bucket().list('4Bdc55j80l8')])"
```

**Expect:** exactly one jpg (~40-60 KB), one row, one object. That is what makes the recovery
permanent for every machine — nobody downloads this frame again.

## 2. It never recovers twice

Same video, same moment, **new** ask string:

```bash
curl -s -X POST http://127.0.0.1:8756/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"4Bdc55j80l8","time":450,"text":"the encoder self-attention block","ask":"UNIQUE-2"}' >/dev/null

curl -s 'http://127.0.0.1:8787/agent/perf?scope=all&limit=2' | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events'][:2]:
    print(f\"{e['frame_source']:>10}  fetch={e['t_frame_fetch_ms']}ms  total={e['t_total_ms']}ms\")"
```

**Expect:**

```
     local  fetch=0ms      total=~2000ms
 recovered  fetch=~9000ms  total=~14000ms
```

Newest first. The second ask is a local hit at 0ms — the frame is on disk now.

## 3. The filename comes from the manifest, not the timestamp

The subtle one, and the most likely thing to regress. `ingest.py` writes `time` as
`round(sec, 1)` but the filename as `int(sec)`, and on 6 frames of `7xTGNNLPyMI` those disagree
outright:

| `t_s` | real file | recomputing from `t_s` would give |
|---|---|---|
| 2431.0 | `f_002430.jpg` | `f_002431.jpg` ✗ |
| 3805.0 | `f_003804.jpg` | `f_003805.jpg` ✗ |

```bash
curl -s -X POST http://127.0.0.1:8756/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"7xTGNNLPyMI","time":2431,"text":"tokenization and the byte pair encoder","ask":"SKEW-1"}' >/dev/null
ls data/7xTGNNLPyMI/frames/
```

**Expect `f_002430.jpg`.** If you see `f_002431.jpg`, the manifest filename is being recomputed
somewhere and roughly a third of the library will 404 against the bucket. `pytest` covers this
too (`test_uses_the_manifest_filename_not_the_timestamp`, `test_key_comes_from_the_filename_not_the_timestamp`).

## 4. The UI offers reprocess on a video that already has widgets

The bug: the ⚡ panel was wrapped in `{!analyzed && ...}`, and `analyzed` flips true as soon as
`concepts.json` has any entries — so on every video browsable at all, the control the error
message names wasn't rendered.

1. Open `$APP/?v=4Bdc55j80l8` (has 1 concept → analyzed).
2. **Expect a `⚡ Reprocess` pill in the top-right header**, beside the engine badge.
3. Click it. The pill becomes a spinner with live step text (`downloading video + transcript +
   keyframes` → `analyzing frames → widgets`).
4. This is the slow path — a full re-download plus a model pass over every frame. Several
   minutes. You don't need to wait it out to call step 2 a pass.

Also check the unanalyzed path still works: `$APP/?v=7xTGNNLPyMI` has 0 concepts, so it should
show the original explanatory card with its own ⚡ button, **not** the header pill.

## 5. A reprocess re-downloads when the manifest has no frames

Before, `_run_ingest` skipped the download whenever `frames.json` existed, so reprocessing one
of these videos went straight to `analyze.py`, errored on every frame, and `SystemExit`'d into
the job as a bare failure.

```bash
uv run python -c "
import serve; from pathlib import Path
print('manifest, no jpgs →', serve._needs_download(Path('data/1HKrqlZmYwM')))
print('manifest + jpgs   →', serve._needs_download(Path('data/5IgOP7Lpk5g')))"
```

**Expect** `True` then `False`. In the UI this is step 4's spinner reaching the *downloading*
step rather than jumping to *analyzing*.

## 6. Reconcile: a no-op reprocess uploads nothing

This is what stops a reprocess from throwing away recovered frames.

```bash
uv run python -c "
import json; from pathlib import Path; import ingest
out = Path('data/9C_XcD-WCTM')                     # 3 frames, all already published
print('uploaded:', ingest.upload_frames('9C_XcD-WCTM', out, json.loads((out/'frames.json').read_text())))"

uv run python -c "
from agent import db; db.load_env()
with db.conn() as c, c.cursor() as cur:
    cur.execute('select count(*) from frames'); print('total rows:', cur.fetchone()[0])"
```

**Expect `uploaded: 0`** and the total row count unchanged (713 plus whatever you've recovered
during testing). A non-zero upload count means it's re-uploading bytes that are already there.

## 7. Negative paths

**Kill switch** — no download attempted, old error returned, fast:

```bash
KEDU_RECOVER_FRAMES=0 uv run serve.py --backend vllm --port 8758 >/tmp/ks.log 2>&1 &
sleep 10
time curl -s -X POST http://127.0.0.1:8758/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"kCc8FmEb1nY","time":1200,"text":"attention","ask":"KS-1"}'
pkill -f "port 8758"
```

**Expect** `"this video's keyframes aren't on disk…"` in ~1.5s (not ~10s), and
`frame_source: "off"` on `/agent/perf`.

**A video YouTube won't serve** — recovery must degrade, never 500. Any private/deleted id
works; expect the same keyframes error with HTTP **200** and `frame_source: "miss"`.

**Bucket is private:**

```bash
set -a; . ./.env; set +a
curl -s -o /dev/null -w 'with secret key: %{http_code}\n' \
  "$SUPABASE_URL/storage/v1/object/frames/EwVfILFo1wQ/f_000000.jpg" \
  -H "apikey: $SUPABASE_SECRET_KEY" -H "Authorization: Bearer $SUPABASE_SECRET_KEY"
curl -s -o /dev/null -w 'no auth        : %{http_code}\n' \
  "$SUPABASE_URL/storage/v1/object/frames/EwVfILFo1wQ/f_000000.jpg"
curl -s "$SUPABASE_URL/rest/v1/frames?select=storage_path&limit=1" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H "Authorization: Bearer $SUPABASE_PUBLISHABLE_KEY"
```

**Expect** `200`, then `400`, then `permission denied for table frames` (code `42501`). The last
one matters: `public.frames` shipped with `grant all … to anon`, so any visitor holding the
publishable key could have deleted every `storage_path`.

**Vite doesn't serve keyframes** (they came from a private bucket; publicDir would republish them):

```bash
for p in "EwVfILFo1wQ/frames/f_000000.jpg" "EwVfILFo1wQ/concepts.json" "pyodide-dist/pyodide-lock.json"; do
  printf '%-40s %s\n' "/$p" "$(curl -s -o /dev/null -w '%{http_code}' "$APP/$p")"
done
cd app && npm run build && cd .. && find app/dist -path '*/frames/*.jpg' | wc -l
```

**Expect** `404`, `200`, `200`, and `0` files after the build.

## 8. The contained analyze path is untouched

Recovery lives in `serve.py` on purpose — `deploy/containment/Dockerfile.analyze` copies
`analyze.py` alone with only `openai` + `pillow`, and has no yt-dlp.

```bash
R=$PWD; T=$(mktemp -d); cp analyze.py "$T/"
(cd "$T" && "$R/.venv/bin/python" -c "
import sys; sys.path=[p for p in sys.path if 'Personal/8kedu' not in p]; sys.path.insert(0,'.')
import analyze; from pathlib import Path
print(analyze.resolve_frame(Path('data/v/frames/f_0.jpg'),'v'))
print('recovery code present?', hasattr(analyze,'_recover_frame'))"); rm -rf "$T"
```

**Expect** `(PosixPath('data/v/frames/f_0.jpg'), 'off', 0)` and `False`.

## 9. Automated suite

```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -q            # expect 54 passed
PYTHONPATH=. KEDU_FRAME_REMOTE=0 uv run --with pytest pytest tests/ -q   # also 54
uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"
cd app && npm run build
```

`PYTHONPATH=.` is required — the tests import `serve` / `ingest` / `agent.*` from the repo root
and there's no packaging. Both env variants must pass: green only with the kill switch on would
mean a test is reaching the network.

## Resetting a video between runs

Recovery is permanent by design, so re-testing the same frame needs a reset. This clears local
jpgs, bucket objects and rows for one video, leaving its manifest and concepts alone:

```bash
uv run python - <<'PY'
import shutil
from pathlib import Path
from agent import db, storage
db.load_env()
vid = "4Bdc55j80l8"          # <-- edit
local = Path("data") / vid / "frames"
n_local = len(list(local.glob("*.jpg"))) if local.exists() else 0
shutil.rmtree(local, ignore_errors=True)
n_obj = storage.remove_video(vid)
with db.conn() as c, c.cursor() as cur:
    cur.execute("delete from frames where video_id=%s", (vid,))
    n_rows = cur.rowcount
    c.commit()
print(f"reset {vid}: {n_local} local jpg(s), {n_obj} object(s), {n_rows} row(s)")
PY
```

Do **not** point this at one of the 16 backfilled videos (`EwVfILFo1wQ`, `6FkRvTtUc-o`,
`5IgOP7Lpk5g`, …) — their jpgs exist on this machine and nowhere else, so deleting them costs
real data. `scripts/scrub_video.py <id>` is the nuclear version: it also drops concepts,
transcripts and the whole `data/<id>/` directory.

There are **31 videos** with a manifest and no pixels anywhere, so you rarely need to reset —
just pick a fresh one:

```bash
uv run python -c "
import json; from pathlib import Path; from agent import db
db.load_env()
with db.conn() as c, c.cursor() as cur:
    cur.execute('select video_id, count(*) from frames group by 1'); rows = dict(cur.fetchall())
for m in sorted(Path('data').glob('*/frames.json')):
    v = m.parent.name
    if not list((m.parent/'frames').glob('*.jpg')) and not rows.get(v):
        print(v, len(json.loads(m.read_text())), 'frames')"
```

## Three gotchas that look like bugs

**1. Reusing an `ask` string proves nothing.** `_prompt_hash` keys on
`PROMPT_VERSION | model | video | frame_file | context | genre` — repeat an ask and you get a
cached spec without the frame path ever running. Every request in a test needs a unique `ask`.

**2. An answer card instead of a widget is the model's call, not a failure.** If the frame is a
talking head or prose slide, the VLM returns `has_concept: false` with an explanation. The
pipeline succeeded: it fetched the frame and the model read it. Judge recovery by
`frame_source: "recovered"` in `/agent/perf` and the jpg on disk, not by the widget type. Prefer
diagram-heavy videos (`4Bdc55j80l8`, `42L1q1Z4Ojc`) if you want to see real widgets.

**3. The cold-miss p50 will cross the 5s red line.** Recoveries are counted in the percentiles
by deliberate choice, and one is ~9s of fetch plus the model call. `?view=agent` will look like
a regression until they age out of the 50-event window. `frame_recover_rate` in
`/agent/perf` is what explains the spike — check it before investigating.

## Known limits, not bugs

- **The 31 metadata-only videos are only fixed frame-by-frame as they're asked for.** A full
  repair still means clicking ⚡ Reprocess.
- `App.jsx:1188`'s hero image hardcodes `kCc8FmEb1nY/frames/f_003780.jpg`, which was never
  captured on any machine — it 404s, and vite now blocks that path anyway.
- `data/5IgOP7Lpk5g` is in `.git/info/exclude` by someone's local choice, so its 33 frames are
  in Supabase while its manifest stays untracked.
- `app/dist` is ~1.1 GB because publicDir copies `video.mkv` too. The app never reads those
  files.
