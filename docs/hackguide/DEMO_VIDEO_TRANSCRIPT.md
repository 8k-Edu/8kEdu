# 8kEdu — Recursive Intelligence demo video transcript

**Project:** 8kEdu  
**Team:** Team 8kEdu  
**Track:** Recursive Intelligence  
**Target runtime:** 4:10–4:35  
**Format:** Loom screen recording, camera on, mostly one continuous take

This script is deliberately built around the track's required proof: the same held-out lecture is
processed once with an empty memory and once after the agent has learned from another teacher. Replace
every bracketed metric with a value from a real recorded run before filming.

## Recording setup

Have these ready before starting Loom:

1. Landing page, with the Karpathy lecture available.
2. One interactive lecture view at an attention or softmax moment.
3. Recursive Intelligence view with an empty/cold state and a learned/warm state.
4. The held-out VisualAI lecture experiment, run against identical frames in both conditions.
5. Agent dashboard with a real heartbeat history and **Wake now** working.
6. OpenShell containment status or the short blocked-egress terminal proof.

Use the same model, prompt version, frame set, and target video for both experiment conditions. The
warm graph may contain Karpathy-derived knowledge, but it must not contain the held-out VisualAI video
before the warm run.

---

## 0:00–0:15 — Team and track

**On screen:** Camera large for the first sentence, then reveal the 8kEdu landing page. Keep the project
name visible.

**Say:**

> Hi, we're Team 8kEdu. I'm **[NAME]**, and I built **[ROLE / COMPONENT]**. **[TEAMMATE NAME]** built
> **[ROLE / COMPONENT]**. We built 8kEdu for the **Recursive Intelligence Track**.

If solo, use:

> Hi, I'm **[NAME]**, the builder behind 8kEdu. I built the learning engine, autonomous agent, and
> interactive app for the **Recursive Intelligence Track**.

## 0:15–0:42 — Elevator pitch

**On screen:** Landing animation: lecture enters the system and interactive artifacts emerge. Briefly
scroll the multi-topic gallery.

**Say:**

> YouTube may be the world's largest classroom, but watching is passive—and every AI tool starts from
> zero on every new lecture. 8kEdu is an autonomous learning agent that watches a lecture, turns its
> teachable moments into live widgets, and remembers the concepts across teachers. As that memory
> grows, the next unseen lecture takes fewer model calls to process while preserving teaching quality.
> It gets measurably better without retraining the model.

## 0:42–1:12 — Show the product before the machinery

**On screen:** Open the Karpathy lecture. Seek to an attention or softmax moment. Drag a value or
temperature slider and show the result recompute. Point briefly to the synchronized video moment and
transcript.

**Say:**

> Here is the learner experience. At this exact moment, the teacher is explaining attention. 8kEdu
> turns the frozen explanation into a live model I can manipulate. The same engine works for matrices,
> plots, financial calculators, and real Python notebooks.
>
> Under the hood, yt-dlp and FFmpeg produce the transcript and keyframes. Nemotron reads both and emits
> a validated concept spec—structured data, not arbitrary interface code. Our React widget kit renders
> that spec deterministically, which keeps the result interactive, grounded, and reliable.

## 1:12–1:47 — First run: the agent forms memory

**On screen:** Switch to `?view=graph`. Start from the cold state, then replay or run ingestion of the
Karpathy source. Show concept nodes appearing and repeated observations collapsing into canonical
nodes such as **softmax**, **self-attention**, and **multi-head attention**.

**Say:**

> On its first run, the agent does not know this domain. It analyzes the lecture and distills each
> useful frame into a canonical concept node. Repeated explanations collapse onto the same node, while
> each teaching moment remains attached as an exemplar.
>
> This graph is the agent's persistent memory: a knowledge graph, compressed experience, and its own
> retrieval source. Supabase preserves it across heartbeat cycles. Nothing here is model retraining.

## 1:47–2:34 — The Recursive Intelligence proof

**On screen:** Display the controlled cold-versus-warm comparison for the held-out VisualAI lecture.
Make the condition labels and identical target/frame count obvious. Animate or run the warm condition,
then hold on the result cards long enough to read them.

**Say:**

> Now we test whether that memory actually changes performance. This VisualAI lecture is held out: the
> graph has never seen it. We process the exact same **[FRAME_COUNT] frames** twice with the same model
> and prompt.
>
> With an empty graph, the cold agent needed **[COLD_CALLS] VLM calls**, took **[COLD_TIME]**, and found
> **[COLD_VALID] valid concepts**. After learning only from a different teacher, the warm agent needed
> **[WARM_CALLS] calls**, took **[WARM_TIME]**, and found **[WARM_VALID] valid concepts** with
> **[WARM_RECALL]% concept recall** against the full sweep.
>
> That is **[CALL_REDUCTION]% fewer model calls** on the same unseen task, with quality held constant or
> improved. This is cross-teacher transfer—not a same-video cache hit.

## 2:34–3:03 — Explain why the improvement is real

**On screen:** Click the **self-attention** node. Show exemplars from Karpathy and VisualAI. Highlight
the selected widget prior/template and the new frame's separately extracted parameters.

**Say:**

> The warm agent recognizes a known concept from the new transcript and frame. It retrieves the widget
> type and successful teaching template from its own history, then extracts the new teacher's actual
> values so the result remains grounded. Novel concepts still go through the full vision path and join
> the graph for the next cycle.
>
> Every new teacher therefore does two jobs: they teach the learner, and they make the agent better at
> understanding future teachers.

## 3:03–3:35 — Show that it is a Claw Agent

**On screen:** Open `?view=agent`. Show the timestamped heartbeat feed, persistent curriculum, and
library totals. Press **Wake now** and let one real decision appear.

**Say:**

> This learning does not wait for a chat prompt. The agent wakes on a heartbeat, reads its persistent
> state, and Nemotron chooses whether to find a source, process a lecture, reinforce the graph, sequence
> a course, or monitor a creator for new uploads. FastAPI exposes the tools, Supabase remembers every
> decision and observation, and Apify supplies fresh channel data. If the model or a tool fails, the
> cycle records the failure and recovers instead of dying.

## 3:35–3:52 — Capability with containment

**On screen:** Show the OpenShell containment card. If reliable, cut to the prepared terminal and run
the shortest proof: approved destination succeeds; `webhook.site` is denied and logged.

**Say:**

> An always-on agent that reaches the web and runs generated notebooks is useful—but dangerous.
> NemoClaw runs it inside OpenShell. YouTube, Apify, Supabase, and local inference are allowed;
> unapproved exfiltration is blocked by policy and written to the audit log. The safety boundary does
> not depend on the model choosing to behave.

## 3:52–4:20 — Product payoff and “so what?”

**On screen:** Return to the graph, click **Best of every teacher**, then show the resulting ordered
course or learner path. End on the product name and the headline recursive delta.

**Say:**

> The product payoff is a course built from the best explanation of each concept—not one teacher's
> playlist. If I struggle with Karpathy's explanation of attention, 8kEdu can offer another teacher's
> exemplar while preserving the prerequisite path.
>
> So what? Learners get active lessons instead of passive video, educators get reusable interactive
> material, and the system becomes cheaper and more capable as the shared library grows. Today it
> learned attention across teachers. Next, the same loop can learn which explanations actually improve
> mastery for each learner. That's 8kEdu: every lecture teaches the student—and the agent.

## 4:20–4:28 — Final identification

**On screen:** Clean end card: **8kEdu · Team 8kEdu · Recursive Intelligence Track · repository URL**.

**Say:**

> We're Team 8kEdu, competing in the Recursive Intelligence Track. Thank you.

---

## Claims that must be proven before recording

- Replace every bracketed metric with values from persisted experiment logs.
- Cold and warm conditions use the same held-out video, frames, model, and prompt version.
- The held-out target is absent from the graph before the warm run.
- Report concept recall or an equivalent quality guardrail alongside speed and call reduction.
- Do not present the same-video Supabase cache as the Recursive Intelligence result.
- If the graph view or best-of-teachers sequencing is not implemented, remove that shot and claim;
  never substitute a mock without labeling it clearly.

## Architecture covered naturally in the narration

- **Frontend:** React + Vite lecture, graph, learner, and agent views.
- **Engine:** yt-dlp + FFmpeg ingestion; transcript/keyframe analysis.
- **Model:** Nemotron vision, canonicalization, reasoning, and agent decisions.
- **Memory:** Supabase concepts, graph, exemplars, learner state, metrics, and run history.
- **Autonomy:** learner and curator heartbeat loops through FastAPI tools.
- **Freshness:** Apify channel monitoring.
- **Containment:** NemoClaw + OpenShell allowlist and audit log.

