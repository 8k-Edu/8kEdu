# 8kEdu — Build Plans (post-hack roadmap, actionable)

Concrete build specs for the four roadmap items. Each: data model → agent/API → UI →
effort → demo-scope. Built on what already exists — `goals`, `curriculum`, `mastery`,
`monitored_channels`, `inference_cache`, `concepts` tables; `agent/loop.py`; `agent/api.py`;
`analyze.py` genre lens; remix = a base64 spec in the URL hash (`#s=`), fully client-side.

Effort key: **S** ≤ half a day · **M** 1–2 days · **L** 3–5 days.
Scope: **demo** (fits the hack) · **partial** (a slice fits) · **post** (after the hack).

---

## R1 — Learn track: dynamic curriculum, Duolingo-style   *(core product · L · partial)*

**Goal.** Learner says *what* to learn → agent proposes course paths from YouTube → learner
picks (or auto-picks) → a Duolingo-style unit map → learn → gen artifact → share → remix.
Mastery tracked, gaps refilled. Everything cached per video·segment·genre.

**The pipeline (5 stages).**
1. **Intake.** "What do you want to learn?" + a type chip (*how-to · concept · subject*).
   → `goals.goal_text` + new `goals.kind`, `goals.level` (beginner/…).
2. **Path proposal.** Agent runs `find_video` × N across the subject, Nemotron clusters +
   ranks into **2–3 paths**: `fast (4 vids)` · `deep (10–12)` · `by-teacher`. Each path = an
   ordered video list + a one-line rationale. Store proposals; learner picks or agent auto-picks.
3. **Curriculum build.** Chosen path → `curriculum` rows (already have `seq`, `state`,
   `rationale`). Add `unit` grouping so a 2-hour lecture becomes several units (by chapter).
4. **Learn loop.** Per unit: play segment → its cached artifacts → a check (quiz from the
   concept). Pass → next unit unlocks. `mastery` row per (learner, concept).
5. **Artifact + share + remix.** Already built — the widget kit, `#s=` remix links. Add a
   per-course "share" that bundles the path.

**Data model (additive — no rewrites).**
```
goals         + kind text, level text, chosen_path_id bigint
paths (new)   id, goal_id, label, rationale, video_ids text[], est_minutes, auto boolean
curriculum    + unit int, lesson_title text        -- group segments into units
mastery       (exists: learner, concept, score) — wire it to quiz results
```

**Agent / API.**
- `agent/loop.py`: new action `PROPOSE_PATHS` (find × N → Nemotron cluster → write `paths`);
  `PROCESS_VIDEO` already fills artifacts; sequencing already exists.
- `agent/api.py`: `POST /agent/goal {text, kind, level}` → intake; `GET /agent/paths` →
  proposals; `POST /agent/choose {path_id}`; `GET /agent/course` → unit map + progress.

**UI.** New `?view=learn`: intake screen → path cards (fast/deep/by-teacher, pick or "let the
agent choose") → **unit map** (linear, locked/unlocked, streak, next-up) → unit view reuses the
existing player + widgets + a check. Duolingo visual language (path spine, XP, streak flame).

**Effort.** L overall. **Demo slice (M):** intake → agent proposes 2 paths live → pick → the
unit map renders from the already-processed Karpathy video split into ~4 units. Skip quizzes/XP.

**Sequence.** (1) `paths` table + `PROPOSE_PATHS` action → (2) `/agent/goal` + `/agent/paths` +
`/agent/choose` → (3) intake + path-cards UI → (4) unit map from `curriculum.unit` →
(5) checks + `mastery` wiring → (6) course share.

---

## R2 — Social + community: remix network   *(growth layer · L · post)*

**Goal.** Public feed of artifacts + courses; **upvote, fork, remix**; creator profiles.
Turns single-player learning into a network where the best artifacts compound. Ties directly
to the Creator market ($250B).

**Foundation that already exists.** A remix is a self-contained base64 spec (`#s=`). Publishing
= persist that spec server-side with a short id + a vote count. Forking = load spec, edit, republish.

**Data model.**
```
profiles (new)   id, handle, display_name, avatar          -- needs real identity (see blocker)
artifacts_pub    id, owner_id, video_id, t_s, spec jsonb, title, remixed_from bigint, created_at
votes            artifact_id, user_id, PRIMARY KEY(artifact_id, user_id)   -- one vote/user
follows          follower_id, followee_id
```
Feed query: `artifacts_pub` left-joined with vote counts, ranked by `hot = votes / age^1.5`.

**API.** `POST /pub/artifact` (publish a spec) · `GET /pub/feed?sort=hot|new` ·
`POST /pub/vote` · `POST /pub/fork` (clone spec → new row, set `remixed_from`).

**UI.** `?view=community`: masonry feed of live artifact cards (each renders its widget),
upvote button, "remix" → opens editor → republish. Profile pages: a creator's artifacts + courses.

**Blocker (why post-hack).** Needs **real identity** — today there's one `demo` learner and no
auth. Real users = Supabase Auth (magic link) + row-level security. That's the gating work;
everything else is CRUD on top. Moderation needed before it's public.

**Effort.** L. **Nothing lands in the demo** beyond what remix links already do — call it out
as the growth roadmap, don't half-build it.

---

## R3 — Breadth of examples, esp. "How-To"   *(credibility · S–M · partial)*

**Goal.** More high-quality pre-baked courses across genres — **How-To** front and center, plus
cooking, fitness, coding tutorials, business. Backs the "any topic, not just code" promise.

**How it works with what's built.** Each genre = an `S_g` lens in [analyze.py](../../analyze.py)
(`GENRE_PROMPTS` + `GENRE_KEYWORDS`). Add a `how_to` lens: the manipulable thing in a how-to is
the **procedure + the numbers/ratios** → notebook calculators + step checklists + before/after.
Then ingest + analyze 3–5 videos, add them to the gallery `CATEGORIES` in `App.jsx`.

**Tasks.**
- Add `how_to` (and e.g. `cooking`, `fitness`) to `GENRE_PROMPTS` / `GENRE_KEYWORDS`.
- Pick 3–5 strong How-To videos; `uv run ingest.py` + `analyze.py --genre how_to` each.
- Upsert to Supabase cache; add to `CATEGORIES` (thumb, count, peek).

**Effort.** S per video once the lens exists (M for the first, incl. lens tuning). **Demo-partial:**
land **one** great How-To course now — it makes the gallery feel general, not AI-only.

**Sequence.** (1) `how_to` lens → (2) ingest+analyze one How-To video → (3) add to gallery →
(4) repeat for more genres as time allows.

---

## R4 — Robust caching for effectiveness   *(the moat, measured · M · partial)*

**Goal.** Make marginal-cost-→0 a **measured** number, not a claim. Harden the cache so identical
work never recomputes; warm popular channels; version on model/prompt change.

**Current state.** Two-tier cache is live: `process_video` checks Supabase `concepts` first
(the video-level moat, proven — 55 widgets reused). But `inference_cache` (frame-level, prompt-hash
keyed, `hits` counter) **exists and is empty** — the fine-grained cache isn't wired yet.

**Build.**
1. **Wire `inference_cache`.** In `analyze.py` / `serve.py`, before a VLM call compute
   `prompt_hash = sha256(genre ⊕ frame_id ⊕ transcript_window ⊕ user_ask)`. Hit → return
   `result`, `hits += 1`. Miss → call model, insert. This catches *identical asks across users*
   at the frame level (video cache only catches whole-video reuse).
2. **Cache-warming.** A heartbeat action `WARM` that pre-processes new uploads on popular
   monitored channels before any learner asks → first learner already has a warm dashboard.
3. **Versioning / eviction.** Add `model` + `prompt_version` to the key; a model/prompt change
   creates new entries instead of serving stale ones. TTL-free (lectures don't change).
4. **Measure.** Dashboard already shows reuse; add a **hit-rate %** and **$ saved** (hits ×
   est-cost-per-inference) so the moat is a live number.

**Effort.** M. **Demo-partial:** wire (1) + surface hit-rate on the dashboard — turns "cached"
into "94% hit rate, $X saved," which sells the commercialization story.

**Sequence.** (1) prompt_hash read/write in the ask path → (2) `hits` increment + dashboard
hit-rate → (3) `WARM` heartbeat action → (4) versioned keys.

---

## Priority given the clock

| # | In demo (T-22h) | Post-hack |
|---|---|---|
| R4 | wire `inference_cache` (1) + hit-rate on dashboard — **cheap, sells commercialization** | warming, versioning |
| R3 | one great **How-To** course — makes it feel general | more genres |
| R1 | intake → agent proposes 2 paths → unit map from Karpathy — **the product vision, live** | quizzes, XP, mastery, course share |
| R2 | — (call it out verbally) | the whole thing (needs auth first) |

**Recommendation:** if any of this lands before freeze, do **R4(1) + R3(one video)** first (hours,
high demo payoff), then the **R1 demo slice** if time. R2 is the "here's where it goes" slide.

---

*Companion:* [`PLAN.md`](PLAN.md) (hack status + roadmap summary) · [`STRATEGY.md`](STRATEGY.md) (bounties).
