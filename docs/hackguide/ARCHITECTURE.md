# 8kEdu — Architecture (component map)

How every component works and contributes. Four views: the whole system, the two autonomous
heartbeats, the video→widgets pipeline, and the live-ask + cache path.

---

## 1. Whole-app structure

```mermaid
flowchart TB
    User(["Learner / Judge"])

    subgraph FE["Frontend — Vite + React (app/src/App.jsx)"]
        Landing["Landing<br/>funnel + carousels + gallery"]
        Lecture["Lecture view<br/>player + timeline + widgets"]
        Learn["?view=learn<br/>Duolingo curriculum"]
        Community["?view=community<br/>remix feed"]
        Dash["?view=agent<br/>live agent dashboard"]
    end

    subgraph API["APIs (FastAPI)"]
        Serve["serve.py :8756<br/>live widget minting + frame cache"]
        AgentAPI["agent/api.py :8787<br/>dashboard · learn · community · tick"]
    end

    subgraph AGENTS["Autonomous agents (heartbeat)"]
        Loop["agent/loop.py<br/>learner: FIND / PROCESS / SEQUENCE / MONITOR"]
        Curator["agent/curator.py<br/>grows the library per genre"]
        Brain["agent/brain.py<br/>Nemotron decide/think"]
        Tools["agent/tools.py<br/>find_video · process_video · monitor_channel"]
    end

    subgraph ENGINE["Engine (video → widgets)"]
        Ingest["ingest.py<br/>yt-dlp + ffmpeg keyframes"]
        Analyze["analyze.py<br/>VLM → concept spec · genre lens Sg"]
    end

    subgraph EXT["External / sponsors"]
        Nemotron["LM Studio :1234<br/>Nemotron-3-Nano-Omni (brain)"]
        YT["YouTube via yt-dlp"]
        Apify["Apify<br/>channel monitoring"]
    end

    subgraph DATA["Supabase (persistence + moat)"]
        Cache["global cache<br/>videos · transcripts · frames · concepts · inference_cache"]
        State["per-user state<br/>learners · goals · curriculum · mastery · paths · monitored_channels · runs"]
        Pub["community<br/>artifacts_pub · votes"]
    end

    subgraph CONTAIN["NemoClaw + OpenShell (scoutclaw)"]
        Policy["8kedu egress policy<br/>allow: youtube · apify · supabase · local-inference<br/>deny + OCSF-log everything else"]
    end

    User --> FE
    Lecture -->|"ask → widget"| Serve
    Learn --> AgentAPI
    Community --> AgentAPI
    Dash --> AgentAPI

    Serve --> Nemotron
    Serve <--> Cache
    AgentAPI <--> State
    AgentAPI <--> Pub
    AgentAPI -->|"wake now"| Loop

    Loop --> Brain --> Nemotron
    Curator --> Brain
    Loop --> Tools
    Curator --> Tools
    Curator --> Ingest --> Analyze --> Cache
    Tools --> YT
    Tools --> Apify
    Tools <--> State
    Analyze --> Nemotron

    Policy -. contains .-> Tools
    Policy -. contains .-> Analyze
    Policy -. governs egress .-> EXT
```

**Reading it:** the frontend is thin — it renders what the agents produce. Two agents run on a
heartbeat (learner + curator), both reason through **Nemotron** and act through sandboxed **tools**.
The engine turns a video into interactive widgets. **Supabase** is both the agent's memory and the
shared cache (the moat). **OpenShell** wraps every tool + engine call — nothing reaches a host
outside the allowlist.

---

## 2. The two autonomous heartbeats

```mermaid
flowchart LR
    subgraph L["Learner loop (agent/loop.py)"]
        direction TB
        L0["heartbeat tick"] --> L1["read state (Supabase)"]
        L1 --> L2["Nemotron decides next action"]
        L2 -->|"no videos"| LF["FIND_VIDEO<br/>yt-dlp search → curriculum"]
        L2 -->|"planned awaits"| LP["PROCESS_VIDEO<br/>engine → widgets (cache-aware)"]
        L2 -->|"course full"| LS["SEQUENCE (stop)"]
        L2 -->|"channels set"| LM["MONITOR<br/>Apify → new upload joins course"]
        LF & LP & LS & LM --> LG["log run → Supabase"]
        LG --> L0
    end

    subgraph C["Curator loop (agent/curator.py)"]
        direction TB
        C0["heartbeat tick"] --> C1["pick least-covered genre"]
        C1 --> C2["Nemotron proposes a query"]
        C2 --> C3["find fresh video (yt-dlp)"]
        C3 --> C4["ingest + analyze with genre lens"]
        C4 --> C5["upsert to global cache"]
        C5 --> C6["log run → Supabase"]
        C6 --> C0
    end
```

Both satisfy the Claw-Agent definition: **wake on a loop, not a prompt**; act unprompted; persist
context in Supabase. The learner grows one course; the curator grows the shared library for everyone.
Both are crash-proof — model unreachable → heuristic fallback, tool failure → logged error run.

---

## 3. The video → widgets pipeline (the funnel)

```mermaid
flowchart LR
    V["YouTube video"] --> ING["ingest.py<br/>yt-dlp + ffmpeg"]
    ING --> KF["keyframes m_i"]
    ING --> TR["transcript Tr_i"]
    G["genre g = G(transcript)"] --> SG["system prompt S_g"]
    KF --> AZ["analyze.py"]
    TR --> AZ
    SG --> AZ
    UC["user context UC_k<br/>(live ask)"] -.-> AZ
    AZ --> M["Nemotron Omni"]
    M --> A["concept spec A_i<br/>widget · params · time"]
    A --> CACHE["Supabase cache<br/>key = (video, segment, genre)"]
    CACHE --> O["dashboard O = Map(⋃A_i, t_i→T_i)"]
    O --> W["live interactive widgets"]
```

The artifact equation: **A_i = M̂(S_g, UC_k, m_i ⊕ f_i..f_n ⊕ Tr_i)**, cached on
`(video, segment, genre)` → computed once, reused by every learner → marginal cost per learner ≈ $0.

---

## 4. Live-ask + two-tier cache

```mermaid
sequenceDiagram
    participant U as Learner
    participant FE as Lecture view
    participant S as serve.py
    participant DB as Supabase cache
    participant N as Nemotron

    U->>FE: select transcript / click frame + ask
    FE->>S: POST /api/widget {text, time, ask, video}
    S->>S: prompt_hash = sha256(genre ⊕ frame ⊕ context)
    S->>DB: inference_cache[hash]?
    alt cache hit
        DB-->>S: stored spec (hits += 1)
        S-->>FE: widget spec (cached=true, ~0ms)
    else miss
        S->>N: frame + context → widget spec
        N-->>S: concept spec JSON
        S->>DB: store spec at hash
        S-->>FE: widget spec
    end
    FE->>U: interactive widget appears
```

Two tiers: **video-level** (`process_video` reuses all of a video's widgets) and **frame-level**
(`inference_cache` catches identical asks across users). The dashboard shows the live hit-rate and
$ saved.

---

*Companion:* [`SUBMISSION.md`](SUBMISSION.md) · [`STRATEGY.md`](STRATEGY.md) · [`PLAN.md`](PLAN.md) · [`../architecture.pdf`](../architecture.pdf) (print version).
