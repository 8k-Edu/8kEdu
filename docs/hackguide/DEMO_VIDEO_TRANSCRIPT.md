# 8kEdu — Recursive Intelligence demo transcript

**Project:** 8kEdu — Lectures You Can Touch

**Team:** Team 8kEdu — Andy Khan and Nickolas Scipione

**Track:** Recursive Intelligence

**Target runtime:** 4:05–4:25

**Format:** Loom, camera on, one continuous product walkthrough

This is the record-ready script. Its metrics match experiment `e9d586862cb6`, persisted in Supabase and visible in `?view=graph`.

## Before recording

1. Start the app with `./run.sh` and confirm the local Nemotron endpoint is available.
2. Open the landing page, a Karpathy attention widget, `?view=graph`, and `?view=agent` in that order.
3. Use the dark theme and a browser width near 1440 px so the graph and run table fit together.
4. Confirm the graph shows 15 concepts, 59 exemplars, two teachers, and the 64 → 8 run delta.
5. Do not click **test unseen teacher**. VisualAI joined the graph after the held-out experiment was recorded.
6. Keep the containment proof ready in a terminal. If it is slow, show the already-persisted status in the agent dashboard.
7. Replace the repository URL on the final end card only if the public URL changes.

## 0:00–0:17 — Team, project, and track

**On screen:** Begin with both cameras large. Reveal the landing page before the final sentence.

**Andy:**

> Hi, we’re Team 8kEdu. I’m Andy Khan. I built the autonomous agent, learning engine, frontend, and containment workflow.

**Nickolas:**

> I’m Nickolas Scipione. I built performance, observability, and database infrastructure. We’re competing in the Recursive Intelligence Track.

**If only one person records:**

> Hi, we’re Team 8kEdu. I’m Andy Khan. My teammate Nickolas Scipione and I built the agent, learning engine, product experience, observability, and infrastructure for the Recursive Intelligence Track.

## 0:17–0:43 — Elevator pitch

**On screen:** Show the landing animation and briefly scroll the multi-topic gallery.

**Say:**

> YouTube may be the world’s largest classroom, but watching is passive. Worse, most AI systems start from zero on every new lecture.

> 8kEdu is an autonomous learning agent that turns lecture moments into live widgets and remembers concepts across teachers.

> As that memory grows, the next unseen lecture needs fewer model calls while preserving concept coverage. The agent gets measurably better without retraining the model.

## 0:43–1:15 — Show the learner experience

**On screen:** Open the Karpathy lecture at an attention or softmax moment. Manipulate the widget and show the synchronized timestamp.

**Say:**

> Here, Karpathy is explaining attention. 8kEdu turns that frozen explanation into a live model I can manipulate beside the original teaching moment.

> The same engine produces matrices, plots, calculators, and real Python notebooks.

> yt-dlp and FFmpeg derive the transcript and keyframes. Nemotron reads each frame with its transcript window and emits a validated concept spec. React renders that structured spec deterministically.

## 1:15–1:48 — Show persistent memory

**On screen:** Open `?view=graph`. Point to the 15 concepts, 59 real frame exemplars, two teachers, and 11 reinforced concepts.

**Say:**

> This is the agent’s persistent memory, built from real model outputs rather than a diagram or slide.

> Each teachable moment is normalized into a concept node. Repeated explanations collapse onto that node, while every source frame remains attached as a grounded exemplar.

> Supabase preserves this graph across runs. It acts as a knowledge graph, compressed episodic memory, and the agent’s own retrieval source.

## 1:48–2:37 — Prove Recursive Intelligence

**On screen:** Trace the learning curve from run one to run two, then hold on the persisted cold and warm rows. Keep the experiment ID and 64-frame denominator visible.

**Say:**

> Now the controlled test. VisualAI was held out when this experiment ran. The target was the same 64-frame lecture in both conditions.

> To keep the comparison reproducible, we replay real cached full-sweep outputs. The cold baseline analyzes all 64 frames, requiring 64 vision-model calls.

> With memory learned only from Karpathy, the warm planner analyzes 15 frames. Seven known moments reuse validated graph exemplars, and eight remain exploration calls for possible novelty.

> That saves 56 calls: an 87.5 percent reduction. Against the full sweep, known-concept recall is 100 percent and retrieval precision is 100 percent.

> This is cross-teacher transfer, not a same-video cache hit. The persisted rows share one experiment ID so the comparison stays auditable.

## 2:37–3:06 — Show the recursive mechanism

**On screen:** Click **Self-attention**. Show both Andrej Karpathy and VisualAI in the exemplar list.

**Say:**

> After the held-out result was recorded, VisualAI was admitted to memory. Self-attention now has 13 exemplars across two teachers.

> On a warm run, transcript overlap ranks frames against known concepts. A known moment retrieves its best validated widget spec. Exploration frames still use the full Nemotron vision path.

> Any valid new observation reinforces the graph for the next run. Every teacher helps the learner now and makes the agent cheaper on future teachers.

## 3:06–3:39 — Architecture, autonomy, and containment

**On screen:** Open `?view=agent`. Show the heartbeat history, persistent curriculum, library, and containment status. Wake the agent only if the local model is already warm.

**Say:**

> This is a Claw Agent, not a chatbot. A heartbeat reads persistent state and chooses the next action: find a source, process a lecture, sequence a course, or monitor a creator.

> FastAPI exposes the tools. Supabase stores decisions, concepts, graph memory, and experiment metrics. Apify supplies fresh channel data, and React presents the learner experience.

> The capable parts run behind NemoClaw and OpenShell policy. Approved services are reachable, while unapproved exfiltration is blocked and written to the audit log.

## 3:39–4:10 — Product payoff and “so what?”

**On screen:** Return to Self-attention in the graph, then briefly show the interactive lecture again.

**Say:**

> If one explanation of attention does not click, 8kEdu can surface another teacher’s grounded exemplar instead of trapping the learner in one playlist.

> Learners get active lessons instead of passive video. Educators get reusable interactive material. The system becomes cheaper and more useful as the shared library grows.

> Today it learned attention across teachers. Next, the same memory can learn which explanations improve mastery for each learner.

> That is 8kEdu: every lecture teaches the student—and the agent.

## 4:10–4:20 — Final identification

**On screen:** End card: **8kEdu · Team 8kEdu · Recursive Intelligence · github.com/8k-Edu/8kEdu**.

**Say:**

> We’re Team 8kEdu, competing in the Recursive Intelligence Track. Thank you.

---

## Claims visible in the recording

- Controlled target: VisualAI, 64 frames, held out before experiment `e9d586862cb6`.
- Cold baseline: 64 frames analyzed and 64 VLM calls.
- Warm plan: 15 frames analyzed, seven graph reuses, and eight exploratory VLM calls.
- Delta: 56 calls saved, 87.5% reduction, 100% known-concept recall, 100% retrieval precision.
- Graph after admission: 15 concepts, 59 exemplars, two teachers, 11 reinforced concepts.
- The comparison is a replay over cached real full-sweep outputs, not a fresh wall-clock benchmark.

## Do not claim or show

- Do not claim a measured cold-versus-warm wall-clock improvement.
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
