# On-demand keyframe recovery, and a reachable reprocess

**Date:** 2026-07-30
**Status:** approved design, pre-implementation
**Branch:** `frame-recovery` (off `frames-in-supabase`, PR #12 — depends on `agent/storage.py`)

## Context

Keyframe jpgs are gitignored, so they exist only on the machine that ran `ingest.py`. PR #12
made them durable in a private Supabase Storage bucket and taught `serve.py`/`analyze.py` to
pull a frame back on a local miss — but it could only backfill what was on one disk. 32 videos
have a git-tracked `frames.json` and pixels nowhere, so a live ask on any of them still
dead-ends:

> this video's keyframes aren't on disk — reprocess it (⚡ Process this video) to enable live asks

Testing that message end to end exposed that both halves of the advice are broken:

1. **The button isn't on screen.** `App.jsx:977` wraps the whole ⚡ panel in
   `{!analyzed && (...)}`, and `analyzed` flips true as soon as `concepts.json` has any entries
   (`App.jsx:595,640`). Every one of these videos has concepts — that's why it's browsable at
   all — so the control the error names is never rendered.
2. **It wouldn't work if it were.** `serve.py:531` gates the download on
   `not (vd / "frames.json").exists()`. The manifest *is* present, so a reprocess skips
   straight to `analyze.py`, every frame raises `FileNotFoundError`, and `analyze.py:620`
   raises `SystemExit("all N frames errored")` into `check=True` → job `state="error"`.

Confirmed against `_yhQg5gFTtQ` ("How to Buy Your First Rental Property in 2025"): manifest
present, 0 local jpgs, 0 objects in the bucket, and telemetry showing
`frame_source="miss", t_frame_fetch_ms=1303` — the fetch ran and the bucket genuinely had
nothing.

The insight this design turns on: **a live ask needs one frame, not 120.** `yt-dlp
--download-sections` fetches a few seconds around a timestamp, measured at **6.8s and 457 KiB**
for the video above, and `ffmpeg` cuts the frame in 65ms at 1280×720 / 45 KB — matching the
library's `scale=-2:720`, `-q:v 3`, 57 KB average. Recovering one frame is ~7s; reprocessing the
video is a ~900s download plus a full model pass.

## Goals

- A click on a frameless moment returns a real widget, without the user learning anything about
  storage.
- Each recovery is permanent and global: the frame lands in the bucket and `public.frames`, so
  no machine ever recovers it again.
- Whole-video processing is always reachable from the video view.
- Recovery failure degrades to exactly today's error, never a 500.

## Non-goals

- Re-ingesting the other 31 metadata-only videos.
- Signed URLs or any browser-side bucket access.
- Changing what the 5s cold-miss label at `App.jsx:2776` claims.

## A. On-demand single-frame recovery

**`ingest.fetch_one_frame(vid, t_s, frame_file, dest_dir) -> Path | None`** — new, owning the
yt-dlp + ffmpeg recipe. It belongs beside `extract_frames` and `upload_frames` because it must
reproduce their exact output; a recovered frame that differs in scale or quality is a frame the
VLM reads differently from its neighbours.

```
LEAD = 2   # seconds of section before the target frame
yt-dlp --download-sections "*{t-LEAD}-{t+5}" --force-keyframes-at-cuts \
       -f "bv*[height<=480]+ba/b[height<=480]/b" -o <tmpdir>/clip.%(ext)s <youtube_url>
ffmpeg -ss {LEAD} -i clip.mp4 -frames:v 1 -vf "scale=-2:720" -q:v 3 <frame_file>
```

**The format selector must match `ingest.download()`'s `height<=480`, not the 720 the feasibility
test used.** `extract_frames` then upscales to `-2:720`, so the whole library is 480p stretched to
720 — a 720p source yields a *sharper* frame than any of its neighbours, and the VLM would be
reading a recovered moment at a fidelity the rest of the video never gets. Matching the selector
makes a recovered frame differ from an extracted one only by the re-encode at the cut.

`--force-keyframes-at-cuts` makes the clip start exactly at the section start, so the seek
offset into the clip is always `LEAD` — not `t`. Clamp the section start at 0 for early frames.
The measurement above used `*205-212` with `-ss 5` for `t=210`; the same arithmetic, written as
a rule.

**The filename is passed in from the manifest, never recomputed from `t_s`.** `ingest.py:116-119`
writes `time` as `round(sec, 1)` but the filename as `int(sec)`, so they disagree on roughly a
third of frames — the same skew that forces object keys to derive from the filename.

**Recovery lives in `serve.py`'s two live handlers, not in `analyze.resolve_frame`.** Three
reasons, each sufficient:

- `resolve_frame` is contracted as cheap and non-raising. A 7s network + subprocess operation
  inside it would silently change the cost of every call site.
- `analyze.py`'s batch loop calls it per frame. 120 sequential recoveries would be catastrophic
  and pointless — the batch path has just downloaded the whole video.
- `deploy/containment/Dockerfile.analyze` copies `analyze.py` alone with only `openai` +
  `pillow`, and has no yt-dlp. Keeping recovery out of that file means the contained path is
  unaffected with no extra guard.

So the live handlers gain a third tier — `local → bucket → recover`. It slots into the existing
`_frame_path(ev, video, fr)` helper, which both handlers already share, so neither handler body
changes:

```python
# serve.py
def _frame_path(ev, video, fr) -> Path:
    src, source, t_fetch = resolve_frame(DATA / video / "frames" / fr["file"], video)
    if source == "miss":
        src, source, t_recover = _recover_frame(video, fr, src)   # None-safe, never raises
        ev["t_frame_fetch_ms"] = t_fetch + t_recover
    ...
```

This sits **after** the cache lookup by construction — `_frame_path` is only reached on a cache
miss, so a cached widget never triggers a download.

On success `_recover_frame` calls `storage.upload_frame` + `db.upsert_frames`, and the request
continues into the model exactly as a normal cold miss would. On any failure it returns the
original absent `src` so the existing `FileNotFoundError` branch fires and the user sees today's
message. The `yt-dlp`-availability check and the `KEDU_RECOVER_FRAMES` read both live in
`_recover_frame`, so there is one place recovery can be switched off.

Guards:

- **Single-flight** on `(video, frame_file)` — N clicks on one moment cause one download.
  Follows the `_jobs_lock` idiom already in `serve.py`.
- **Hard subprocess timeout** (~60s), independent of `KEDU_TIMEOUT` for the same pile-up reason
  `analyze.py:325-329` documents.
- **`KEDU_RECOVER_FRAMES=0`** kill switch, and off automatically where `yt-dlp` is absent.
- Recovery is attempted **before** `spend_credit`, consistent with the frame resolve it extends.

## B′. A reprocess keeps the frames it already has

`(video_id, t_s)` is already the identity of a frame — it is `public.frames`' primary key. Today
`publish_frames` passes `prune=True`, so a reprocess calls `storage.remove_video` and re-uploads
every frame, discarding recovered ones and their rows for nothing. Replace that with a
reconcile against the new manifest:

| new manifest has `t_s` | `public.frames` has `t_s` | action |
|---|---|---|
| yes | no | upload the object, insert the row |
| yes | yes, same `storage_path` | **skip** — already published |
| yes | yes, different `storage_path` | upload under the new name, update the row, delete the old object |
| no | yes | true orphan — delete object and row |

This is why `prune=True` existed: a re-extract at a different interval renames every frame and
orphans the old keys. The reconcile handles that case in its last row without throwing away the
frames that *did* survive, which is what your point asks for.

`extract_frames` itself can't skip frames — it is one ffmpeg pass over the whole video
(`fps=1/interval`), and the download dominates the cost regardless — so the saving here is the
redundant upload of ~120 objects and, more importantly, the preservation of frames that have
already been analyzed.

**Known consequence.** Skipping the upload leaves the bucket holding the recovered bytes while
local disk now holds freshly-extracted ones for the same key. Both are the same moment, and
`_prompt_hash` keys on the *filename* — never on frame content, and nothing in the repo hashes
frame bytes — so every machine still serves one consistent cached spec. With the 480p selector
above, the two differ only by a re-encode. Accepted rather than solved: making them identical
would mean re-downloading the frame we already have.

`t_s` equality is exact float comparison on a `double precision` PK. `round(sec, 1)` is
deterministic for a given interval, so this holds while the duration reading is stable; if the
interval shifts, every `t_s` differs and everything is treated as new — which is correct, they
are different frames. Note the pre-existing hazard: `duration_sec()`'s ffprobe-less fallback
returns `1200.0`, which would shift the interval and orphan the whole set.

## B. Fix the reprocess gate

`serve.py:531` becomes "no manifest **or** no jpgs":

```python
if not (vd / "frames.json").exists() or not any((vd / "frames").glob("*.jpg")):
```

A reprocess of a metadata-only video then actually re-downloads, and — because `ingest.py`
publishes — repopulates the bucket for everyone.

## C. Make whole-video processing reachable

Lift the ⚡ trigger out of the `{!analyzed && ...}` wrapper at `App.jsx:977`. Unanalyzed videos
keep the explanatory card unchanged; analyzed videos get a compact reprocess control in the
video header, wired to the same `processVideo` and the same `/api/ingest/status` polling. No
navigating away, no pasting a URL.

## Telemetry

`frame_source` gains `"recovered"`, and `/agent/perf` gains `frame_recover_rate` beside the
existing `frame_remote_rate` / `frame_miss_rate`.

Recoveries are **counted in the cold-miss percentiles** — a deliberate choice of honest numbers
over a protected one. The consequence, stated so nobody debugs it later: a handful of recoveries
will push `t_total_p50_ms` past the 5s threshold the dashboard draws a red line at
(`App.jsx:2756,2776`), and it will look like a regression until they age out of the window.
`frame_recover_rate` is what makes that spike explainable.

## Testing

Unit, network patched:

- miss → recover → `upload_frame` called, `upsert_frames` called, real path returned,
  `frame_source="recovered"`.
- recovery raises / returns None → response is today's exact error dict, HTTP 200, credit
  refunded when metered.
- two concurrent asks for one frame → exactly one download.
- `KEDU_RECOVER_FRAMES=0` → no download attempted, `frame_source` stays `"miss"`.
- filename comes from the manifest: a frame whose `time` and filename disagree recovers under
  its manifest name.
- gate fix: manifest present + zero jpgs takes the download branch.
- reconcile: a reprocess whose manifest matches existing `(video_id, t_s)` rows uploads nothing
  and deletes nothing; one whose interval shifted uploads the new set and deletes exactly the
  orphaned objects; a recovered frame present in both is left untouched.

Integration: `_yhQg5gFTtQ` at t≈210 through `/api/widget` — a real widget, one new object in the
bucket, one new `frames` row, and a second identical ask served from local disk.

## Risks

- **yt-dlp against YouTube is a moving target.** Blocks, geo-restrictions, deleted and private
  videos all fail for reasons unrelated to this code, which is why degrading to the existing
  error is the load-bearing behaviour rather than an afterthought.
- **Each recovery is a real download.** Bounded by single-flight and by never needing to happen
  twice for the same frame, but a user scrubbing across a frameless video will trigger several.
  The kill switch is the release valve.
- **Recovered frames come from a re-encoded cut.** Matching `ingest.download()`'s `height<=480`
  selector and the shared `scale=-2:720` / `-q:v 3` recipe makes them equivalent to their
  neighbours in resolution and quality, but not byte-identical. This costs nothing in rework:
  recovery happens once per frame (it lands on disk, in the bucket and in `public.frames`), and
  the widget cache keys on the filename, so a recovered frame is never re-recovered and never
  re-analyzed.
