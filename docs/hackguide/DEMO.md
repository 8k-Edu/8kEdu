# 8kEdu — Loom recording runbook

Target: **4:05–4:25**, camera on, one continuous walkthrough. Read the exact narration in [`DEMO_VIDEO_TRANSCRIPT.md`](DEMO_VIDEO_TRANSCRIPT.md).

## Start and verify

```bash
./run.sh
```

Confirm the local Nemotron endpoint is up. Open `http://dev.localhost:5174/` and prepare these tabs:

1. Landing page.
2. Karpathy lecture at a working attention or softmax widget.
3. `/?view=graph`.
4. `/?view=agent`.
5. Optional containment terminal.

The graph must show:

- 15 concepts and 60 real frame exemplars.
- Two teachers and 11 reinforced concepts.
- Cold: 64/64 frames, 64 VLM calls.
- Warm: 15/64 frames, seven reuses, eight VLM calls.
- 87.5% fewer actual calls, 88.3% less elapsed time, and 100% known-concept recall.

Do **not** click **test unseen teacher** while recording. VisualAI is already in the graph because the valid held-out experiment ran before admission.

## Recording order

### 1. Team and hook — 0:00–0:43

Introduce Andy Khan, Nickolas Scipione, Team 8kEdu, and the Recursive Intelligence Track. Pitch passive video → interactive learning + persistent cross-teacher memory.

### 2. Product — 0:43–1:15

Manipulate a live widget beside the synchronized Karpathy lecture. Name yt-dlp, FFmpeg, Nemotron, validated specs, and React.

### 3. Persistent memory — 1:15–1:48

Open the graph. Point to concepts, exemplars, teachers, and reinforced nodes. Explain knowledge graph + compressed episodic memory + self-RAG.

### 4. Recursive proof — 1:48–2:37

Trace the over-time curve from run one to run two, then hold on the cold/warm rows. State that this is an executed pair under experiment `p20260719a`, not a planned replay.

Say the exact delta: **64 calls and 553.1 s cold → eight calls and 64.7 s warm + seven graph reuses; 87.5% fewer calls; 88.3% less time; 100% known recall and precision.**

### 5. Mechanism — 2:37–3:06

Click Self-attention. Show Andrej Karpathy and VisualAI together. Explain transcript matching, validated spec reuse, exploration, and graph reinforcement.

### 6. Agent and containment — 3:06–3:39

Open the agent dashboard. Show persisted heartbeat decisions and containment. Wake the agent only if the model is already warm.

### 7. “So what?” — 3:39–4:20

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
