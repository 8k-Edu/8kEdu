# 8kEdu — Recursive Intelligence plan

**Track:** "Build an agent that measurably gets smarter the more it runs."
**Judged on:** performance delta (first run → last run: completion time, accuracy, decision quality) + a clear learning mechanism (knowledge graph / RAG-from-self-context / compressed episodic memory).

8kEdu hits all three bonus mechanisms with **one** structure: a **cross-teacher concept knowledge graph** built as the byproduct of the widget pipeline. This doc is the buildable plan.

---

## 1. The core idea

Every frame the engine processes yields a concept observation (`{widget, title, explanation, params}` at `video, t_s`). Today we render the widget and discard the linkage. Instead:

- The **concept behind the frame** becomes a graph node.
- The **same concept taught by different teachers** collapses onto one node, each frame a cross-teacher *exemplar*.
- Processing a new video then **reuses** known nodes instead of regenerating → the agent gets faster, sharper, better-sequenced the more it runs.

The graph is simultaneously: the **knowledge graph**, the **compressed episodic memory** (every past frame distilled into nodes), and the substrate for **RAG-from-self-context** (retrieve a known concept's exemplar instead of re-inferring).

Real overlap exists in the cache **today**: Karpathy (`kCc8FmEb1nY`) and VisualAI (`42L1q1Z4Ojc`) both teach attention / softmax / multi-head → the first build produces genuine cross-teacher edges.

---

## 2. Data model

```sql
-- canonical concept nodes, scoped to a topic (e.g. 'generative_ai')
kg_concept(
  id bigserial pk, topic text, name text,            -- canonical slug, e.g. 'softmax'
  label text,                                         -- display, e.g. 'Softmax / probability normalization'
  exemplar_count int default 0,
  best_link_id bigint,                                -- the exemplar to serve by default
  first_run int,                                      -- which run this node first appeared (for the delta)
  created_at timestamptz default now(),
  unique(topic, name))

-- each frame (any teacher) that teaches a concept — the cross-teacher exemplars
kg_frame_link(
  id bigserial pk, kg_concept_id bigint, concept_id bigint,   -- concept_id → existing concepts.id
  video_id text, t_s real, channel text, widget text,
  quality real default 0, created_at timestamptz default now())

-- concept → concept relationships
kg_edge(topic text, src_id bigint, dst_id bigint,
  kind text,                                          -- 'prereq' | 'related'
  weight int default 1, primary key(topic, src_id, dst_id, kind))

-- episodic memory rollup: which widget kind validates for which concept
kg_widget_prior(concept_name text, widget text,
  tried int default 0, valid int default 0, primary key(concept_name, widget))

-- the recursion metric log — one row per processing run
topic_runs(
  id bigserial pk, topic text, run_seq int, video_id text, channel text,
  frames_analyzed int, vlm_calls int, widgets_new int, widgets_reused int,
  novel_concepts int, known_concepts int, build_ms int, yield real,
  created_at timestamptz default now())
```

Reuses existing `concepts` (frame → widget spec) and `runs` (episodic history). No rewrites.

---

## 3. Build pass — `kg_build(topic)`  (agent/kg.py)

1. Pull all `concepts` for the topic's videos.
2. **Canonicalize** each concept name with Nemotron: *"map this concept to a short canonical label"* → `softmax`. Cache the mapping (title → canonical) to avoid re-calling.
3. **Dedupe / link:** match canonical name to an existing `kg_concept` (exact + fuzzy). Match → insert `kg_frame_link` (new exemplar, `exemplar_count++`). No match → new `kg_concept` (record `first_run`).
4. **Edges:** concepts co-occurring in the same video within a time window → `related` (weight++). Then one batched Nemotron call labels `prereq` direction on the top-weighted edges.
5. **best_link** per concept: highest `quality` exemplar (completeness of params / reuse count).

Idempotent — safe to re-run as the curator adds videos.

---

## 4. How processing USES the graph — the recursion mechanism (analyze/tools)

When processing a **new** video under topic T:

- **A. Frame ranking (fragment/find).** Score each frame by transcript-window overlap with known concept names in the graph; analyze top-ranked first; stop when K consecutive frames yield nothing new (coverage plateau). *Cold graph = uniform sweep. Warm = targeted → fewer calls, higher yield.*
- **B. Concept retrieval (generate widgets).** For each detected concept: canonicalize → look up `kg_concept`. **Known** → link this frame as another exemplar + reuse the best exemplar's spec (adapt params) → **0 / cheap VLM call**. **Unknown** → full VLM generate → add node. *This is RAG-from-self-context.*
- **C. Episodic widget-kind prior.** Bias generation toward the widget kind that historically validated for this concept (`kg_widget_prior`) → higher first-try validity.
- **D. Log** `frames_analyzed, vlm_calls, widgets_new/reused, novel/known_concepts, build_ms, yield` → `topic_runs`.

---

## 5. The defined task + the measured delta

**Task:** "process the next video on topic T into teachable widgets + place it in the course."
**Method:** replay a topic's videos in order (`run_seq` 1..N). A domain's concept set is finite, so later runs hit more known nodes.

| Metric (per run) | Direction | Why |
|---|---|---|
| VLM calls / video | ↓ | known concepts retrieved, not regenerated |
| build time (ms) / video | ↓ | RAG-from-self-context |
| yield (valid widgets ÷ frames analyzed) | ↑ | graph ranks which frames matter |
| first-try widget validity | ↑ | episodic widget-kind prior |
| novel-concept rate | ↓ | domain saturates → agent "knows the shape" |
| exemplars / concept | ↑ | cross-teacher coverage grows |
| prereq violations in the course | ↓ | topological sort of prereq edges |

**First run vs last run on these = the delta the judges score.** Anchor points already real: Karpathy = 55 concepts cached; 2nd learner on it = **0 VLM calls**.

**Honesty guardrail:** the delta must come from real overlap → retrieval. No hardcoded "warm is faster." A run with genuinely no overlap won't improve — and we report that honestly.

---

## 6. The demo  (`?view=graph`)

- **Left — the knowledge graph, live.** Force-directed. Concept nodes sized by `exemplar_count`, edges = prereq/related. Replay the topic's videos: new nodes pop green; reinforced nodes pulse and their exemplar count ticks up. Click `softmax` → "explained by Karpathy 57:11 · VisualAI 3:10" (cross-teacher exemplars with channel labels).
- **Right — the delta.** Run-over-run table + sparklines: VLM calls, build time, yield, novel-concept rate. Headline: **"Run 1: 20 min, 9% yield, random order. Run 8: 2 min, 60% yield, correct prerequisites — same task, no retraining."**
- **Replay button** — fast-forwards the topic ingestion (or steps through the cached `topic_runs`) so the graph densifies on camera.

Product payoff shown in the same view: stuck on one teacher's softmax → the node offers every other teacher's version; the sequencer auto-assembles a **"best of every teacher"** course (best exemplar per concept, prereq order).

---

## 7. Build tiers

| Tier | What | Files | Payoff |
|---|---|---|---|
| **T1 — KG engine** | schema + `kg_build(topic)`: canonicalize → dedupe → link → edges. Run on existing Karpathy+VisualAI concepts → real cross-teacher links | `agent/db.py`, `agent/kg.py` | the graph exists, off real data |
| **T2 — recursion metrics** | `topic_runs` logging in the processing path; graph-guided retrieval (§4 A/B); replay a topic in order → the declining-cost curve | `agent/kg.py`, `analyze.py`/`tools.py`, `agent/api.py` | the judged delta |
| **T3 — the viewer** | `?view=graph`: force-directed KG + cross-teacher exemplars + delta panel + replay button | `app/src/App.jsx`, `/agent/graph` endpoint | the wow |
| **T4 — bonus** | episodic widget-kind prior (`kg_widget_prior`) → first-try validity; prereq topological course sequencing | `agent/db.py`, `analyze.py`, `agent/loop.py` | accuracy + decision-quality deltas |

**Recommended order given the freeze:** T1 → T3 (graph visible off real data — the wow) → T2 (the measured delta — the judging core) → T4 if time.

---

## 8. Endpoints (agent/api.py)
- `GET /agent/graph?topic=` → `{nodes, edges, exemplars}` for the viewer.
- `POST /agent/kg/build?topic=` → run `kg_build`, return node/edge counts.
- `GET /agent/recursion?topic=` → `topic_runs` rows (the delta curve).
- `POST /agent/recursion/replay?topic=` → replay the topic's videos in order (demo), streaming run metrics.

---

*Companion:* [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`SUBMISSION.md`](SUBMISSION.md) · [`STRATEGY.md`](STRATEGY.md) · [`ROADMAP.md`](ROADMAP.md).
