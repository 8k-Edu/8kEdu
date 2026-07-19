# 8kEdu — Loom recording runbook

Target: **3:40–4:00**, camera on, one continuous walkthrough. Read the exact narration in [`DEMO_VIDEO_TRANSCRIPT.md`](DEMO_VIDEO_TRANSCRIPT.md).

## Start and verify

```bash
./run.sh
```

Confirm the local Nemotron endpoint is up. Open `http://dev.localhost:5174/` and prepare these tabs:

1. Landing page.
2. Karpathy paused at `1:04:02` with **Self-Attention Query-Key Affinity** selected.
3. `/?view=graph`.
4. `/?view=agent`.
5. Optional containment terminal.

Wait for every tab to finish loading before opening Loom. The graph should have **Self-attention** selected, and the agent dashboard should show persisted heartbeat data rather than its initial zero-value placeholders. Do not reload prepared tabs during the take.

The graph must show:

- 71 concepts and 163 real frame exemplars.
- Eight videos from seven named teachers.
- Cold: 64/64 frames, 64 VLM calls.
- Warm: 15/64 frames, seven reuses, eight VLM calls.
- 87.5% fewer actual calls, 88.3% less elapsed time, and 100% known-concept recall.

Do **not** click **test unseen teacher** while recording. VisualAI is already in the graph because the valid held-out experiment ran before admission.

## Recording order

### 1. Team and hook — 0:00–0:35

Introduce Andy Khan, Nickolas Scipione, Team 8kEdu, and the Recursive Intelligence Track. Pitch passive video → interactive learning + persistent cross-teacher memory.

### 2. Product — 0:35–1:15

Drag the attention temperature slider once beside the synchronized Karpathy lecture. Name yt-dlp, FFmpeg, Nemotron, validated specs, and React.

### 3. Persistent memory — 1:15–1:40

Open the graph. Point to the eight-video source library, then choose Self-attention from the concept dropdown. Show its 23 exemplars across four videos and four teachers. Explain knowledge graph + compressed episodic memory + self-RAG.

### 4. Recursive proof — 1:40–2:25

Trace the over-time curve from run one to run two, then hold on the cold/warm rows. State that this is an executed pair under experiment `p20260719a`, not a planned replay.

Say the exact delta: **64 calls and 553.1 s cold → eight calls and 64.7 s warm + seven graph reuses; 87.5% fewer calls; 88.3% less time; 100% known recall and precision.**

### 5. Mechanism — 2:25–2:48

Click Self-attention. Show Andrej Karpathy, VisualAI, GoodLearningMachines, and Krish Naik together. Explain transcript matching, validated spec reuse, exploration, and graph reinforcement.

### 6. Agent and containment — 2:48–3:16

Open the agent dashboard. Show persisted heartbeat decisions and containment. Wake the agent only if the model is already warm.

### 7. “So what?” — 3:16–3:57

Return to the cross-teacher exemplars. Close on active learning, reusable educator material, and the system becoming cheaper as memory grows.

## Truth guardrails

- Attribute measured runtime only to experiment `p20260719a` and its recorded settings.
- Do not call 100% known-concept recall “overall recall”; overall cold-concept recall is 66.7%.
- Do not claim new-frame parameter adaptation; warm retrieval currently copies a validated prior spec.
- Do not describe the recursive result as a same-video cache hit.
- Do not claim Nemotron canonicalizes concepts; canonicalization is deterministic.
- Do not show or mention a “Best of every teacher” button or prerequisite-sorted course.

## If something fails

- Keep the graph tab loaded before starting Loom; it reads the persisted proof from Supabase.
- If the local model is cold, do not press **Wake now**. Narrate the already-persisted heartbeat rows.
- If containment is slow, show its persisted dashboard status and explain the prepared allowlist/block proof.
- If the widget API drops, use an already-loaded interactive widget; the recursive proof remains available through the agent API.
