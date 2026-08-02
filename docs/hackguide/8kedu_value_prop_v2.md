# 8kEdu — Value Proposition v2

## Problem statement

> Self-directed learners do their serious studying on YouTube — the world's largest library of expert technical teaching — but video is built for watching, not learning. Every hour of lecture costs another hour of manual labour: pausing to rebuild code, redraw plots, hunt prerequisites and manufacture practice, because the teaching happens **on screen**, and every AI study tool they own reads only the transcript.

*(Who: self-directed technical learners. Where: YouTube. Why it matters: hours of repeated manual work per session and weak retention. How often: every study session. No solution named — per the problem-statement rules.)*

---

## The value proposition

**Primary — customer-facing**
> Turn any educational video into an interactive course you can practice, run, and master.

**Product-true — the site's own tagline, use it everywhere**
> An autonomous agent watches any lecture — and makes it touchable.

**Technical / investor**
> 8kEdu understands educational video at the frame and segment level, converts visual explanations into validated interactive learning objects, and connects concepts across creators into a knowledge graph that makes the system cheaper and sharper the more it runs.

**The 30-second spoken version**
> The best technical teaching in the world is on YouTube, and it's free — but it's passive. Serious learners pause every few minutes to rebuild the code, redraw the plot, and hunt the prerequisite, because their AI tools read the transcript while the teaching happens on screen. 8kEdu watches the video itself. It turns the exact moment a concept is taught into something you can run, drag and practice — and it remembers that concept across every teacher who ever taught it.

---

# 1. Customer profile

**Beachhead segment:** self-directed learners using YouTube for technical, visual subjects — university students, developers, engineers, researchers, and professionals studying AI, programming, mathematics, statistics, data science, and adjacent how-to skills.

## Customer jobs

**Functional.** Understand a hard concept from a long video; find the exact moment it is explained; convert explanations into usable artifacts (notebooks, plots, notes, exercises); learn topics in prerequisite order; connect equivalent explanations across creators; verify understanding rather than merely finishing; resume later where they stopped.

**Emotional.** Feel that time watching produced real progress; escape the understand-then-forget cycle; feel less overwhelmed by the volume of content; gain confidence they are sequencing correctly; feel capable of advanced material without buying a course.

**Social.** Demonstrate skill through completed notebooks and projects; keep current in a fast-moving field; share widgets, notes, and learning paths with peers.

## Pains — ranked

**P1 · The pause-and-rebuild tax.** *Severity: daily, hours.* Watching MIT OpenCourseWare, Andrew Ng, or Karpathy seriously means stopping every few minutes to retype code into Jupyter, reproduce a plot, copy a formula, or search a prerequisite. The work is valuable and entirely repetitive. This pain is founder-authentic: it is why the product exists.

**P2 · The tools read words, not pictures.** *Severity: structural.* The dominant AI study tools summarize the caption track. The diagram being drawn, the code being executed, the derivation on the whiteboard — anything that lives in the picture rather than the transcript — is invisible to them.

**P3 · Watched is not learned.** *Severity: chronic.* Video completion creates familiarity, not mastery. There is no active recall, no practice, no progress signal, no proof.

**Secondary pains.** Concepts trapped in time (endless timeline scrubbing); learning fragmented across creators — one has the intuition, another the mathematics, a third the implementation; recommendations ordered by engagement rather than prerequisites; constant context-switching across YouTube, Jupyter, ChatGPT, and notes. *The fragmentation pain is secondary as felt, but it is what powers the cross-teacher graph — the moat.*

## Gains (beyond pain inversion)

Learners leave with a **portfolio** — notebooks, widgets, exercises — not a watch history. They get a **best-of composite**: the clearest intuition, strongest derivation, and most useful implementation drawn from different teachers. Any high-quality free video gains **course structure**. And the system **improves with use** — theirs and everyone else's.

---

# 2. Value map

*Split honestly, per the roadmap. Investors trust a "next" column far more than an undifferentiated feature list.*

## Live today — shipped and demoable

- Ingestion from YouTube (yt-dlp + ffmpeg): transcript, keyframes, chapters.
- Frame-and-segment vision analysis with **genre lenses** — AI/STEM, finance, real estate, how-to, cooking, fitness — so a cooking video is read differently from a maths lecture.
- **Validated concept specs, never generated code**: the model emits schema-checked data; a deterministic widget kit renders it. Reproducible, cacheable, safe.
- Live widgets: matrices, attention maps, softmax, function plots; **runnable notebooks** (real numpy + matplotlib in the browser, sliders wired to variables); drag-a-box on any diagram to make that region its own widget.
- Every widget is a **shareable, forkable URL** — remix needs no account.
- **Cross-teacher knowledge graph**: 71 concepts, 163 grounded exemplars across 8 lectures from 7 teachers; the same concept from different teachers collapses to one node with every source moment kept as evidence.
- **Two-tier cache** keyed on (video, segment, genre) — 184 widgets across 23 videos reused by every learner; live hit-rate and cost dashboard.
- **Autonomous loops**: a learner agent (find → process → sequence → monitor) and a curator agent growing the shared library, both on a heartbeat, contained by an egress allowlist.
- Learn-track slice: state a goal → the agent proposes two real course paths → unit map. Community feed slice: publish, upvote, fork.

## Building next — schema ready, not shipped

Quizzes and active recall wired to per-concept mastery; streaks and progress; **prerequisite-sorted "best of every teacher" course assembly**; real identity and moderation for the community; cache warming and version-keyed eviction.

## Pain relievers, tied to pains

- **P1 →** The rebuild work is automated: code becomes a runnable notebook, a plot becomes an interactive widget, at the timestamp where it is taught.
- **P2 →** The pipeline reads frames in transcript context — the visual explanation itself becomes the learning object, with a link back to the exact moment as evidence.
- **P3 →** *Today:* artifacts force doing, not just watching — you run the notebook, drag the matrix. *Next:* quizzes and mastery tracking close the loop. (Stated as next, deliberately.)
- **Secondary →** Concept search replaces scrubbing; the graph supplies another teacher's explanation when one doesn't land; one workspace replaces five tools.

---

# 3. Product–customer fit, with evidence

| Customer pain | 8kEdu response | Evidence today |
| --- | --- | --- |
| "I understand the video but can't apply it." | Runnable notebooks and manipulable widgets. | Live — pyodide notebooks with real numpy; Karpathy's attention at 1:04:02 becomes a draggable matrix. |
| "I can't find where the concept was explained." | Every artifact pinned to its exact frame and timestamp. | Live — source links on every widget spec. |
| "I need three videos to understand one topic." | Cross-teacher concept graph. | Live — self-attention node holds 23 exemplars from 4 teachers. |
| "AI tools only summarize the transcript." | Frame-level vision with genre lenses. | Live — the entire pipeline; the incumbent architecture (caption-track reading) cannot see frames at all. |
| "I spend hours recreating plots and notes." | Artifacts generated automatically, cached for everyone. | Live — 184 widgets across 23 videos, reused at ~zero marginal cost. |
| "YouTube doesn't teach in prerequisite order." | Prerequisite edges in the graph; topologically sorted courses. | Partial — seeded prereq edges render today; sorted course assembly is next. |
| "I watched it but don't know if I learned it." | Quizzes, active recall, mastery per concept. | **Next** — schema exists (`mastery`), wiring is the near-term build. |
| *(System-level)* "Does this get better or just bigger?" | The graph reuses known concepts instead of re-inferring. | **Measured** — experiment p20260719a: held-out lecture, 64 → 8 model calls (−87.5%), 553.1 s → 64.7 s (−88.3%), 100% known-concept recall and retrieval precision; overall cold recall 66.7%, reported alongside. |

*The last row is the one no competitor's canvas can write.*

---

# 4. Why this beachhead

The technical-learner segment is where the visual-to-interactive transformation is most valuable and most verifiable: code and plots become *demonstrably* interactive; correctness of generated notebooks is checkable; learners already live in notebooks and AI tools; the creator supply (Karpathy, 3Blue1Brown, MIT OCW, Andrew Ng) is deep and high-quality; willingness to pay is career-driven; and the problem is personally authentic to both founders. Expand later into professional training, test prep, repairs, and broader how-to — the genre-lens system already spans six categories.

*Note: "AI tutoring in every local language" is the three-year horizon (the Sensei vision), not the beachhead. Leading with it at pre-seed would dilute a sharp wedge into a broad promise. The canvas stays on technical learners; the multilingual tutor is where the graph eventually takes us — and Andy's BanglaLLaMA work is the credibility for that arc when asked.*

---

# 5. Alternatives and differentiation

- **YouTube** — the content, none of the structure: no curriculum, practice, prerequisites, or mastery.
- **Coursera / Udemy / Khan Academy** — excellent structure, closed catalog. 8kEdu adds structure to the *open* video web.
- **NotebookLM and transcript-first study tools** — read the caption track; no audio fallback of their own; slides, demos, and on-screen code are invisible, and videos without usable captions fail outright. This is an architecture, not a missing feature.
- **OpusClip** — long video → short clips. 8kEdu: long video → learning experience.
- **TwelveLabs** — general video-understanding infrastructure. 8kEdu is the education application and the learning graph on top: sequencing, practice, mastery, and a compounding concept memory no infrastructure vendor accumulates.

---

# 6. Business customer canvas (creators · universities · platforms)

**Their jobs.** Convert existing video libraries into interactive courses; improve completion; add chapters, quizzes, notebooks, and search without instructional-design headcount; make archives discoverable; see which concepts learners struggle with.

**Their pains.** Interactive course production is expensive; old libraries are unnavigable; manual chaptering and quiz authoring need teams; views are weak evidence of learning; long videos get abandoned.

**8kEdu's value.** Automatic library-to-courseware conversion at low marginal cost; frame- and concept-level semantic search; learner analytics and mastery signals; old content newly discoverable and monetizable; a video-to-course **API**.

**Pricing (aligned with the deck):** Creator $49/month · Institution $20–50K/year, seat-based · API usage-based · consumer Pro $12/month.

---

# 7. Assumptions → experiments, ranked by risk

| # | Assumption (riskiest first) | Test | Status |
| --- | --- | --- | --- |
| 1 | Interactive artifacts measurably improve learning outcomes over plain video. | **E2 — outcome A/B:** one group watches the video, one uses the 8kEdu version; compare quiz scores, completion, 7-day recall. | Untested. **Until E2 runs, every speed claim stays about compute, not comprehension** — "8× fewer model calls" is measured; "understand 8× faster" is not. |
| 2 | Technical learners will pay for repeated use. | **E3 — real checkout:** free = one converted video; **$12/month** = unlimited + saved courses + paths. Measure checkout, not surveys. | Untested. Priced to match the deck. |
| 3 | Generated widgets are accurate enough without heavy human review. | **E-QA:** human spot-check a sample of specs per genre; track validity rate. | Partially evidenced — 100% known-concept recall/precision on p20260719a, but 66.7% overall cold recall says review still matters. |
| 4 | Creators welcome transformation rather than fearing loss of control. | **E4:** hand three educational creators interactive versions of their own videos; ask embed / license / pay. | Untested — also the answer to the content-rights question. |
| 5 | Learners want interaction more than summaries. | **E1:** process ten flagship lectures; measure widget/notebook interaction vs. summary reading, with source-link click-through as the trust signal. | Untested. |
| 6 | Cross-video matching adds value beyond single-video processing. | **E5:** one topic (attention), one multi-source path vs. best single video; measure preference and completion. | Graph exists; learner preference untested. |
| 7 | Multimodal processing cost supports consumer pricing. | Ongoing measurement. | **Largely de-risked** — local open-model inference at $0 API spend; cache dashboard shows reuse; the $3K cloud incident is why the architecture is local-first. |

---

## Final positioning

> **YouTube contains many of the world's best teachers, but it was built for watching, not learning. 8kEdu turns their videos into interactive courses.**
