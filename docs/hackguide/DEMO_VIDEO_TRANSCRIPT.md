# 8kEdu — Recursive Intelligence demo transcript

**Project:** 8kEdu — Lectures You Can Touch

**Team:** Team 8kEdu — Andy Khan and Nickolas Scipione

**Track:** Recursive Intelligence

**Target runtime:** 3:40–4:00

**Format:** Loom, camera on, one continuous product walkthrough

This is the record-ready script. Its metrics match executed experiment `p20260719a`, persisted in Supabase and visible in `?view=graph`.

## Before recording

1. Start the app with `./run.sh` and confirm the configured inference endpoint is available.
2. Open the landing page, Karpathy at `1:04:02` with **Self-Attention Query-Key Affinity** selected, `?view=graph`, and `?view=agent` in that order.
3. Use the dark theme and a browser width near 1440 px so the graph and run table fit together.
4. Confirm the graph shows 71 concepts, 163 exemplars, eight videos, seven teachers, and the 64 → 8 actual-call delta. Leave **Self-attention** selected.
5. Do not click **test unseen teacher**. VisualAI joined the graph after the held-out experiment was recorded.
6. Keep the containment proof ready in a terminal. If it is slow, show the already-persisted status in the agent dashboard.
7. Wait for the agent dashboard to replace its initial zero-value placeholders with persisted heartbeat data. Do not reload any prepared tab after Loom starts.
8. Replace the repository URL on the final end card only if the public URL changes.

## 0:00–0:15 — Team, project, and track

**On screen:** Start with camera large, then reveal the landing page.

**Say:**

> Hi, we’re Team 8kEdu. I’m Andy Khan. My teammate Nickolas Scipione and I built the agent, recursive learning engine, product, observability, and infrastructure. We’re competing in Recursive Intelligence.

## 0:15–0:35 — Elevator pitch

**On screen:** Show the landing animation and gallery.

**Say:**

> YouTube may be the world’s largest classroom, but watching is passive, and most AI systems start from zero on every new lecture.

> 8kEdu turns lecture moments into interactive widgets and remembers concepts across teachers. As that memory grows, unseen lectures need fewer model calls without retraining the model.

## 0:35–1:15 — Learner experience

**On screen:** Switch to Karpathy paused at `1:04:02` with **Self-Attention Query-Key Affinity** already selected. Drag the temperature slider once and show the synchronized teaching moment.

**Say:**

> Here, Karpathy is explaining attention. 8kEdu turns that frozen explanation into a live model I can manipulate beside the original teaching moment.

> That is our dense-knowledge example: self-attention becomes a manipulable matrix instead of a static diagram.

> For an everyday goal like learning Excel, the same engine can turn formulas, ranges, and calculations into an editable spreadsheet you practice while the instructor explains them.

> yt-dlp and FFmpeg extract transcripts and keyframes. Nemotron reads each frame with its transcript context and emits a validated concept spec. React renders it deterministically as matrices, plots, calculators, or Python notebooks.

## 1:15–1:40 — Persistent memory

**On screen:** Open `?view=graph`, sweep across the source library, then select Self-attention.

**Say:**

> This is the agent’s persistent memory: 71 concepts and 163 grounded moments across eight real lectures from seven teachers.

> Equivalent explanations collapse onto one concept node, but every source frame remains attached as evidence. Supabase preserves this graph across runs and makes it the agent’s retrieval source.

## 1:40–2:25 — Recursive Intelligence proof

**On screen:** Trace the learning curve, then hold on the cold and warm rows. Keep the experiment ID and 64-frame denominator visible.

**Say:**

> Now the controlled test. VisualAI was held out, and both conditions used the same 64-frame lecture.

> We created a fresh isolated topic seeded only with Karpathy. Cold sent all 64 frames through Nemotron: 64 actual calls in 553.1 seconds.

> Warm used the same frames, model, prompt, image settings, token budget, temperature, and concurrency. Seven known moments reused graph exemplars, leaving eight actual calls in 64.7 seconds.

> That is 87.5 percent fewer calls and 88.3 percent less time, with 100 percent known-concept recall and retrieval precision.

> VisualAI entered memory only after both conditions finished. Both rows share experiment ID p20260719a, making the comparison auditable.

## 2:25–2:48 — Recursive mechanism

**On screen:** Show Self-attention exemplars from Karpathy, VisualAI, GoodLearningMachines, and Krish Naik.

**Say:**

> Self-attention now has 23 grounded exemplars across four videos and four teachers.

> On a warm run, transcript overlap ranks frames against known concepts. Known moments retrieve validated widget specs; uncertain frames still use Nemotron vision. Every valid observation then reinforces the graph for the next teacher.

## 2:48–3:16 — Autonomy and containment

**On screen:** Open `?view=agent`. Show heartbeat history, persistent state, and containment status. Do not wake the model.

**Say:**

> This is a Claw Agent, not a chatbot. Its heartbeat reads persistent state and chooses whether to find a source, process a lecture, sequence a course, or monitor a creator.

> FastAPI exposes its tools; Supabase stores decisions and memory; Apify supplies fresh channel data. NemoClaw and OpenShell allow approved services while blocking and auditing attempted exfiltration.

## 3:16–3:50 — “So what?”

**On screen:** Return to Self-attention, then briefly show the interactive lecture.

**Say:**

> If one explanation does not click, 8kEdu can surface another teacher’s grounded example instead of trapping the learner in one playlist.

> Learners get active lessons, educators get reusable interactive material, and the system becomes cheaper as its shared memory grows.

> Today it learned attention across teachers. Next, it can learn which explanations improve mastery for each student.

> That is 8kEdu: every lecture teaches the student—and the agent.

## 3:50–3:57 — Final identification

**On screen:** End card: **8kEdu · Team 8kEdu · Recursive Intelligence · github.com/8k-Edu/8kEdu**.

**Say:**

> We’re Team 8kEdu, competing in Recursive Intelligence. Thank you.

---

## Claims visible in the recording

- Controlled target: VisualAI, 64 frames, held out before experiment `p20260719a`.
- Cold: 64 actual calls, 553.1 seconds, zero errors.
- Warm: 15 selected frames, seven graph reuses, eight actual calls, 64.7 seconds, zero errors.
- Delta: 87.5% fewer calls, 88.3% less elapsed time, 100% known recall and retrieval precision.
- Overall cold-concept recall: 66.7%.
- Graph after post-experiment expansion: 71 concepts, 163 exemplars, eight videos, seven teachers.

## Do not claim or show

- Do not generalize the measured runtime beyond experiment `p20260719a` and its recorded settings.
- Do not call known-concept recall overall recall; the two metrics are intentionally separate.
- Do not say the warm path extracts new parameters; it currently reuses the best validated prior spec.
- Do not call the held-out result a same-video cache hit.
- Do not click **test unseen teacher** after VisualAI is already in the graph.
- Do not mention a **Best of every teacher** button or prerequisite-sorted course; those are next steps.
- Do not say Nemotron performs canonicalization. The current canonicalizer is deterministic and auditable.

## Architecture covered by the narration

- **Frontend:** React + Vite lecture, graph, learner, and agent views.
- **Engine:** yt-dlp + FFmpeg ingestion and transcript/keyframe analysis.
- **Model:** Nemotron vision for widget generation and reasoning for agent decisions.
- **Memory:** Supabase concepts, graph nodes, exemplars, run metrics, and learner state.
- **Recursion:** deterministic canonicalization, transcript matching, self-RAG spec reuse, and exploration.
- **Autonomy:** learner and curator heartbeat loops through FastAPI tools.
- **Freshness:** Apify channel monitoring.
- **Containment:** NemoClaw + OpenShell allowlist and audit log.
