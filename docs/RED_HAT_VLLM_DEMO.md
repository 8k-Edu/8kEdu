# 8kEdu × vLLM — Red Hat five-minute demo

This is the record-ready runbook for a five-minute screen share to a mixed technical Red Hat audience.

The thesis is simple: **8kEdu turns passive lectures into interactive software, and vLLM makes the multimodal inference pipeline practical under concurrent load.**

The demo uses upstream vLLM through the `vllm-metal` plugin on Apple Silicon. It does not claim to run Red Hat AI Inference Server. The connection is the serving architecture: Red Hat AI Inference builds on vLLM and highlights the same PagedAttention and continuous-batching economics.

- [Red Hat AI Inference](https://www.redhat.com/en/products/ai/inference-server)
- [Red Hat explanation of PagedAttention and continuous batching](https://docs.redhat.com/en/documentation/red_hat_ai_inference_server/3.2/html/getting_started/about-getting-started_getting-started)

## Demo URLs

- Lesson: <http://localhost:5173/?v=5IgOP7Lpk5g>
- Live engine dashboard: <http://localhost:5173/?view=perf>
- Recorded throughput artifact: [`perf.html#throughput`](perf.html#throughput)
- PagedAttention A/B: [`perf.html#paged-attention`](perf.html#paged-attention)

The lesson is a 5:31 Excel alignment tutorial. The primary moment is **Excel Column Formatting Options** at `2:22`, where the learner can edit a spreadsheet while the instructor explains Wrap Text and Shrink to Fit.

## What must work

| Priority | Feature | Stage proof | Fallback |
| --- | --- | --- | --- |
| P0 | Excel lesson | Video seeks to `2:22`; the spreadsheet renders and cells remain editable. | [`excel-widget.png`](assets/redhat-vllm-demo/excel-widget.png) |
| P0 | Vision engine | `qwen3-vl-4b` is served on `:8000`. | Recorded benchmark artifact |
| P0 | Reasoning engine | `deepseek-r1-distill-qwen-7b` is served on `:8001`. | Explain the two-role architecture over the static engine capture. |
| P0 | Concurrent frame analysis | Twelve attempts complete with zero errors and no 503 responses. | Skip the command and use the throughput chart. |
| P0 | Live observability | Both engine cards show model, queue, KV, preemption, token, and cache metrics. | [`vllm-engine-live.png`](assets/redhat-vllm-demo/vllm-engine-live.png) |
| P1 | PagedAttention | Native paged-attention kernel appears in the server log; the concurrent workload remains stable. | [`paged-attention.png`](assets/redhat-vllm-demo/paged-attention.png) |
| P1 | Continuous batching | Multiple keyframes are in flight and the batch finishes without drops. | [`vllm-throughput.png`](assets/redhat-vllm-demo/vllm-throughput.png) |
| P1 | Prefix caching | Repeating the batch produces nonzero prefix-cache queries and hits. | Mention it as enabled; do not invent a hit percentage. |
| P1 | Structured output | The batch emits valid concept JSON. | Use the four prepared spreadsheet specifications. |
| P1 | OpenAI-compatible multimodal API | The unchanged client sends base64 images through `/v1/chat/completions`. | Explain verbally; do not open source code during the five minutes. |
| P1 | Warmup and bounded requests | The first stage request does not absorb kernel compilation and slow requests cannot accumulate indefinitely. | Omit reliability claims if the rehearsal does not verify them. |

Authentication, community, containment, agent heartbeat, cloud inference, and widget persistence are outside this presentation. Do not spend the final bug-bash on them.

## Day-before setup

### 1. Configure the demo profile

Set these non-secret values in the private `.env` file. Do not display that file while sharing the screen.

```dotenv
KEDU_BACKEND=vllm
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=qwen3-vl-4b
NEMOTRON_BASE_URL=http://localhost:8001/v1
NEMOTRON_MODEL=deepseek-r1-distill-qwen-7b
```

The two-engine Metal profile uses Qwen3-VL for video frames and DeepSeek-R1 for agent reasoning because the Metal plugin does not serve Nemotron Omni's MoE architecture.

### 2. Make keyframes available in a development worktree

The portable transcript, chapters, frame manifest, duration, and prepared widgets are tracked. The JPGs remain private and ignored. When presenting from a worktree, link the existing keyframe directory:

```bash
export PRIMARY_CHECKOUT=/path/to/your/8kedu
ln -s "$PRIMARY_CHECKOUT/data/5IgOP7Lpk5g/frames" data/5IgOP7Lpk5g/frames
```

Skip this when `data/5IgOP7Lpk5g/frames/f_000000.jpg` already exists.

### 3. Start and warm vLLM

From terminal one:

```bash
./scripts/serve-vllm-metal.sh
```

Wait for both `warmed :8000` and `warmed :8001`. Confirm the vision log contains `Native paged-attention Metal kernels loaded`.

### 4. Start 8kEdu

From terminal two:

```bash
./run.sh
```

On the feature branch, Vite serves the application at `localhost:5173`.

### 5. Run the presentation preflight

```bash
./scripts/preflight-redhat-demo.sh
```

Do not present until it ends with `RED HAT DEMO READY`.

### 6. Exercise the concurrent path twice

```bash
KEDU_CONCURRENCY=8 KEDU_MAX_TOKENS=1024 \
uv run analyze.py --backend vllm --video 5IgOP7Lpk5g \
  --limit 12 --max-px 512 \
  --out-name /tmp/redhat-vllm-demo.json
```

Require `errors=0`. Repeat the command and confirm that the engine dashboard shows nonzero prefix-cache queries and hits. The output belongs in `/tmp`; do not overwrite the prepared lesson.

### Verified rehearsal — August 17, 2026

- Both vllm-metal engines started, warmed, and reported `awake`.
- Both concurrency-eight runs completed 12/12 model attempts with valid spreadsheet output, zero errors, zero 503 responses, and zero preemptions.
- The first run took 54.0 seconds (`0.22 frames/s`); the repeat took 46.4 seconds (`0.26 frames/s`). These are health results from the current host, not replacements for the committed benchmark.
- The live capture observed six running and two queued requests, 11% KV-cache use, and 66 generated tokens/s.
- After both runs, cumulative prefix-cache counters were 31,869 queried tokens and 26,192 hits; multimodal-cache counters were 25 queries and 12 hits.

### 7. Prepare the browser

Use a browser width near 1440 px, disable notifications, hide bookmarks, close developer tools, and preload these tabs in order:

1. Excel lesson at `2:22`, paused with **Excel Column Formatting Options** selected.
2. `?view=perf`, scrolled so both engine cards fit.
3. `docs/perf.html#throughput`.
4. `docs/perf.html#paged-attention`.
5. A terminal with the 12-frame command typed but not started.

Do not reload the prepared lesson after screen sharing begins.

## Five-minute run of show

### 0:00–0:25 — Outcome first

**On screen:** Excel tutorial at `2:22`, spreadsheet widget visible.

**Say:**

> 8kEdu turns a passive tutorial into something the learner can manipulate beside the instructor. Here the instructor is explaining Excel alignment, and the lesson has become a working spreadsheet.

### 0:25–1:05 — Touch the lecture

**On screen:** Select the `December` cell. Toggle Wrap Text or Shrink to Fit, then edit one value.

**Say:**

> This is not a screenshot. The learner can change the same kind of object the instructor is teaching. 8kEdu paired the transcript with the video keyframe, generated a validated spreadsheet specification, and rendered it with deterministic React components.

### 1:05–1:35 — The serving contract

**On screen:** Hold on the lesson.

**Say:**

> The inference request contains a base64 keyframe and the surrounding transcript. Our client asks an OpenAI-compatible vLLM endpoint for schema-constrained JSON. That stable API let us change the serving engine without rewriting the product.

### 1:35–1:45 — Create real load

**On screen:** Run the prepared terminal command and switch immediately to the performance dashboard.

**Say:**

> A lecture gives us independent keyframes, so the useful workload is concurrent, not one prompt at a time.

### 1:45–2:55 — Show vLLM working

**On screen:** Live vision and brain cards.

**Say:**

> These are the two live vLLM engines: Qwen3-VL reads the lecture frames, and DeepSeek-R1 handles agent reasoning. PagedAttention stores each request's KV cache in reusable pages. Continuous batching fills the engine as requests arrive, chunked prefill keeps a large image prompt from monopolizing a step, and prefix caching reuses our fixed instruction prefix. Here we can see running and queued work, KV use, preemptions, tokens per second, and cache activity instead of treating inference as a black box.

### 2:55–4:05 — The iterative throughput result

**On screen:** Horizontal concurrent-sweep bars.

**Say:**

> Our first vLLM integration reached single-request parity with the previous server: about 1.33 seconds versus 1.40. The larger win appeared when we used the scheduler properly. On the vllm-mlx path, throughput rose from 0.40 to 0.67 frames per second at concurrency eight—a 1.70× gain with zero drops. With native vllm-metal and PagedAttention, the measured workload rose from 0.17 to 0.47 frames per second—a 2.70× gain with zero drops. The absolute rates came from different host conditions, so the honest comparison is each engine against its own sequential baseline.

### 4:05–4:30 — What PagedAttention bought

**On screen:** PagedAttention off/on bars.

**Say:**

> On the same host, enabling PagedAttention increased admitted KV-cache concurrency for 8,000-token sequences from 1.00× to 9.78×. That is capacity headroom, not a 9.78× latency claim. It is what made the stable concurrency-eight run possible.

### 4:30–4:48 — Layer the efficiencies

**On screen:** Return to the Excel widget.

**Say:**

> 8kEdu also remembers validated concepts, so the application can eliminate model calls before they reach the server. In one separate controlled run that reduced actual calls from 64 to 8. Application memory removes work; vLLM serves the remaining work efficiently.

### 4:48–5:00 — Close

**Say:**

> 8kEdu turns lectures into software, and vLLM makes the self-hosted multimodal pipeline practical as load grows. Thank you.

## Metrics and attribution

| Recorded result | Safe claim |
| --- | --- |
| Cold widget `5.7 s → 1.9 s → 1.33 s` | The entire release progression is 4.3×. Downscaling and caching caused the first reduction; the final `1.9 → 1.33` step adopted vllm-mlx. |
| vllm-mlx `0.40 → 0.58 → 0.67 frames/s` | Continuous batching reached 1.47× at concurrency four and 1.70× at concurrency eight with zero drops. |
| vllm-metal `0.17 → 0.40 → 0.47 frames/s` | The native path reached 2.33× at concurrency four and 2.70× at concurrency eight with zero drops. |
| PagedAttention `1.00× → 9.78×` | This is admitted KV-cache concurrency capacity for 8,000-token sequences, not throughput or latency. |
| vLLM `1.33 s` versus LM Studio `1.40 s` | This establishes single-request parity. The headline is concurrent throughput. |
| Recursive run `64 → 8` calls | Application-level reuse eliminated calls; vLLM did not independently cause this reduction. |
| Warm cache `280×` and region re-ask `400×` | These are application-cache results, not vLLM results. |

The repository preserves the chart values, method notes, and commits, but not the original raw benchmark logs. Treat the charts as recorded results. A rehearsal batch is a health check unless it recreates the original protocol and environment.

## Failure handling

- If the concurrent workload or dashboard does not react within three seconds, switch to the recorded charts. Do not debug on stage.
- If one engine card is offline, use the static engine capture and speak in the past tense: “In the verified rehearsal…”
- If YouTube playback fails, show the prepared widget capture. The tracked lesson specifications still prove the output contract.
- If the local model is cold, do not wait for it. Skip the live command.
- If time slips past a cue by more than ten seconds, omit the application-memory statistic and go directly to the close.

## Fallback captures

### Interactive Excel lesson

![Excel alignment lesson with editable spreadsheet](assets/redhat-vllm-demo/excel-widget.png)

### Live vLLM engines

![vLLM vision and brain engine dashboard](assets/redhat-vllm-demo/vllm-engine-live.png)

### Concurrent throughput

![vLLM sequential, concurrency-four, and concurrency-eight throughput](assets/redhat-vllm-demo/vllm-throughput.png)

### PagedAttention capacity

![PagedAttention off versus on KV-cache concurrency capacity](assets/redhat-vllm-demo/paged-attention.png)

## Final checklist

- [ ] Power connected; memory-heavy applications closed.
- [ ] Both engines warmed before opening the call.
- [ ] `./scripts/preflight-redhat-demo.sh` is green.
- [ ] Twelve-frame workload completed twice with zero errors.
- [ ] Prefix-cache queries and hits are nonzero.
- [ ] Excel lesson is paused at `2:22` with the correct widget selected.
- [ ] Performance tabs are already scrolled to the correct charts.
- [ ] Terminal contains no secrets or unrelated history.
- [ ] Fallback images open locally.
- [ ] Rehearsal finishes by `4:35`.
