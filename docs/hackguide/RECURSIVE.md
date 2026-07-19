# 8kEdu — Recursive Intelligence plan and implementation status

**Track:** "Build an agent that measurably gets smarter the more it runs."
**Judged on:** performance delta (first run → last run: completion time, accuracy, decision quality) + a clear learning mechanism (knowledge graph / RAG-from-self-context / compressed episodic memory).

8kEdu hits all three bonus mechanisms with **one** structure: a **cross-teacher concept knowledge graph** built as the byproduct of the widget pipeline. This doc records both the design and what shipped.

## Shipped proof

| Evidence | Current result |
|---|---|
| Persistent graph | 15 concepts · 59 real frame exemplars · 2 teachers · 11 reinforced concepts |
| Controlled target | VisualAI lecture · 64 frames · held out before experiment `e9d586862cb6` |
| Cold baseline | 64 frames analyzed · 64 VLM calls |
| Warm plan | 15 frames analyzed · 7 graph reuses · 8 exploratory VLM calls |
| Delta | 56 calls saved · 87.5% reduction · 100% known-concept recall · 100% retrieval precision |
| Viewer | `?view=graph`, backed by persisted Supabase graph and run rows |

The benchmark replays cached real full-sweep outputs. It measures retrieval coverage and planned VLM calls, not fresh paired wall-clock runtime.

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
2. **Canonicalize** each concept with deterministic aliases plus exact/fuzzy matching. The current demo covers the attention-domain overlap without spending another model call.
3. **Dedupe / link:** match canonical name to an existing `kg_concept` (exact + fuzzy). Match → insert `kg_frame_link` (new exemplar, `exemplar_count++`). No match → new `kg_concept` (record `first_run`).
4. **Edges:** concepts co-occurring in one video within four minutes become weighted `related` edges. A small audited seed map supplies the current `prereq` edges.
5. **best_link** per concept: highest `quality` exemplar (completeness of params / reuse count).

Idempotent — safe to re-run as the curator adds videos.

---

## 4. How processing USES the graph — the recursion mechanism (analyze/tools)

When processing a **new** video under topic T:

- **A. Frame ranking (fragment/find).** Score transcript windows against known graph concepts, retain separated high-confidence matches, and reserve 12.5% of the frame set for exploration. *Cold = full sweep. Warm = retrieval plus exploration.*
- **B. Concept retrieval (generate widgets).** A known moment reuses the best validated exemplar spec at the new timestamp. Exploration frames use the full vision path; valid outputs then reinforce the graph. *This is RAG-from-self-context.*
- **C. Episodic widget-kind prior.** `kg_widget_prior` records tried and valid widget kinds. Feeding that prior back into generation is a next step, not part of the measured delta.
- **D. Log** `frames_analyzed, vlm_calls, widgets_new/reused, novel/known_concepts, build_ms, yield` → `topic_runs`.

---

## 5. The defined task + the measured delta

**Task:** "process the next video on topic T into teachable widgets + place it in the course."
**Method:** replay a topic's videos in order (`run_seq` 1..N). A domain's concept set is finite, so later runs hit more known nodes.

| Metric (per run) | Direction | Why |
|---|---|---|
| VLM calls / video | ↓ | known concepts retrieved, not regenerated |
| planned VLM calls / video | ↓ | RAG-from-self-context |
| yield (valid widgets ÷ frames analyzed) | ↑ | graph ranks which frames matter |
| first-try widget validity | ↑ | episodic widget-kind prior |
| novel-concept rate | ↓ | domain saturates → agent "knows the shape" |
| exemplars / concept | ↑ | cross-teacher coverage grows |
| prereq violations in the course | ↓ | topological sort of prereq edges |

**Cold versus warm calls, with recall and precision beside them, form the judged delta.** The controlled replay is persisted under one experiment ID so the conditions remain auditable.

**Honesty guardrail:** the delta must come from real overlap → retrieval. No hardcoded "warm is faster." A run with genuinely no overlap won't improve — and we report that honestly.

---

## 6. The demo  (`?view=graph`)

- **Graph — persistent memory, live.** Nodes are sized by `exemplar_count`; edges distinguish related and prerequisite links. Click Self-attention to show Karpathy and VisualAI exemplars together.
- **Delta — persisted cold/warm rows.** The cards show 64→8 planned calls, 87.5% reduction, and 100% known-concept recall. Both rows share experiment `e9d586862cb6`.
- **Demo controls.** `learn Karpathy` builds the initial memory; `test unseen teacher` records the held-out replay and then admits VisualAI. Do not rerun the held-out button after admission when filming.

Product payoff shown in the same view: if one teacher's explanation does not click, the node offers grounded moments from another teacher. Prerequisite-sorted “best of every teacher” course assembly is the next product step.

---

## 7. Build tiers

| Tier | What | Files | Payoff |
|---|---|---|---|
| **T1 — KG engine ✅** | schema + `kg_build(topic)`: canonicalize → dedupe → link → edges. Run on Karpathy+VisualAI → real cross-teacher links | `agent/kg.py` | the graph exists, off real data |
| **T2 — recursion metrics ✅** | `topic_runs` logging; graph-guided retrieval; held-out replay with recall and precision | `agent/kg.py`, `analyze.py`, `agent/api.py` | the judged delta |
| **T3 — the viewer ✅** | `?view=graph`: knowledge graph + cross-teacher exemplars + delta panel + controls | `app/src/App.jsx`, `/agent/graph` | the wow |
| **T4 — partial** | widget prior is persisted and prereq edges render; generation bias and topological sequencing remain | migration, `agent/kg.py` | next accuracy/decision delta |

**Recommended order given the freeze:** T1 → T3 (graph visible off real data — the wow) → T2 (the measured delta — the judging core) → T4 if time.

---

## 8. Endpoints (agent/api.py)
- `GET /agent/graph?topic=` → `{nodes, edges, exemplars}` for the viewer.
- `POST /agent/kg/build` → build a topic from supplied video IDs and return node/edge counts.
- `GET /agent/recursion?topic=` → `topic_runs` rows (the delta curve).
- `POST /agent/recursion/replay` → record one cold/warm held-out replay and optionally admit the target to the graph.

---

*Companion:* [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`SUBMISSION.md`](SUBMISSION.md) · [`STRATEGY.md`](STRATEGY.md) · [`ROADMAP.md`](ROADMAP.md).
