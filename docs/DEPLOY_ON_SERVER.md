# Deploy 8kEdu on a Linux server

A complete, copy-pasteable guide to run 8kEdu on a normal Linux box (Ubuntu/Debian
assumed). **No GPU or Apple hardware required** — inference runs on the cloud
(OpenRouter) via API key, so the whole app, agent brain, and curator heartbeat run
anywhere.

> macOS-only bits (Apple-Silicon `vLLM`/MLX for *free local* inference, and the
> NemoClaw/OpenShell Docker sandbox for *containment*) are intentionally not part of a
> Linux deploy — they stay on the developer machine. The `mlx-vlm` dependency is marked
> `darwin`-only, so `uv sync` skips it on Linux automatically.

---

## 0. Architecture on the server

| Process | Port | What it serves |
|---|---|---|
| `serve.py --backend openrouter` | 8756 | live widget generation (`/api/*`) |
| `agent/api.py` | 8787 | dashboards + community (`/agent/*`, `/pub/*`) |
| `agent/curator.py` (optional) | — | autonomous heartbeat that grows the library |
| `nginx` | 80/443 | static frontend + reverse-proxy to the two APIs + serves `data/` |
| Supabase | (cloud) | shared cache, learner state, community, credits |
| OpenRouter | (cloud) | the vision + reasoning model (via API key) |

Everything talks to Supabase (already cloud) and OpenRouter (cloud). The server holds
no model weights.

---

## 1. System prerequisites

```bash
sudo apt-get update
sudo apt-get install -y git curl ffmpeg nginx

# uv (Python package/venv manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env      # or restart shell

# Node 22 (for the frontend build)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Verify: `uv --version`, `node --version` (>=22), `ffmpeg -version`.

---

## 2. Clone + install

```bash
cd /opt
sudo git clone https://github.com/8k-Edu/8kEdu.git
sudo chown -R $USER:$USER 8kEdu
cd 8kEdu

uv sync                          # creates .venv, installs deps (mlx skipped on Linux)
cd app && npm install && cd ..
```

---

## 3. Configure `.env` (cloud inference — the important part)

Create `/opt/8kEdu/.env`. This makes the **entire agent** — vision, widget generation,
and the reasoning brain — run on OpenRouter with your API key:

```bash
# ── Supabase (shared cache + community + credits) ─────────────────────────────
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxx
SUPABASE_SECRET_KEY=sb_secret_xxx
SUPABASE_DB_URL=postgresql://postgres.<project-ref>:<db-password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres

# ── Cloud inference via OpenRouter (NO local model needed) ────────────────────
KEDU_ALLOW_CLOUD=1                         # unlocks cloud backends (cost guard)
KEDU_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx       # <-- your OpenRouter key
OPENROUTER_MODEL=google/gemini-2.5-flash   # any OpenRouter vision model

# Agent brain (decisions + curator search queries) → same OpenRouter endpoint
NEMOTRON_BASE_URL=https://openrouter.ai/api/v1
NEMOTRON_MODEL=google/gemini-2.5-flash
NEMOTRON_API_KEY=sk-or-v1-xxxxxxxx         # same key as above

# ── Session ───────────────────────────────────────────────────────────────────
AGENT_HANDLE=server
```

> **How it works:** `serve.py`/`analyze.py` read `KEDU_BACKEND=openrouter` +
> `OPENROUTER_API_KEY`; `agent/brain.py` (the claw-agent's reasoning) reads
> `NEMOTRON_BASE_URL`/`NEMOTRON_MODEL`/`NEMOTRON_API_KEY`. Point all of them at
> OpenRouter and there is zero local-model dependency. `.env` is gitignored — never
> commit it.

**Rotate the key** if it was ever shared in plaintext.

---

## 4. Database

The schema lives in `supabase/migrations/`. Apply it once against your Supabase project:

```bash
# Option A — Supabase CLI (recommended)
supabase link --project-ref <project-ref>
supabase db push

# Option B — psql, run each migration in order
for f in supabase/migrations/*.sql; do psql "$SUPABASE_DB_URL" -f "$f"; done
```

(Optional) seed credits for a demo user — cloud generation costs 1 credit each:

```sql
insert into learners(handle, credits) values ('server', 1000)
on conflict (handle) do update set credits = 1000;
```

---

## 5. Build the frontend

```bash
cd /opt/8kEdu/app
npm run build           # → app/dist (static site)
cd ..
```

Rebuild after any frontend change. The build uses relative API paths (`/api`, `/agent`,
`/pub`), so nginx routing (below) is all that's needed — no build-time API URL.

---

## 6. Run the backends (systemd)

Create `/etc/systemd/system/kedu-serve.service`:

```ini
[Unit]
Description=8kEdu widget API (serve.py)
After=network-online.target

[Service]
WorkingDirectory=/opt/8kEdu
ExecStart=/opt/8kEdu/.venv/bin/python serve.py --backend openrouter --port 8756
Restart=always
User=%i

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/kedu-api.service`:

```ini
[Unit]
Description=8kEdu dashboard/community API (agent.api)
After=network-online.target

[Service]
WorkingDirectory=/opt/8kEdu
ExecStart=/opt/8kEdu/.venv/bin/python -m agent.api
Restart=always
User=%i

[Install]
WantedBy=multi-user.target
```

(Optional) autonomous heartbeat `/etc/systemd/system/kedu-curator.service` — the
claw-agent growing the library on cloud inference:

```ini
[Unit]
Description=8kEdu curator heartbeat
After=network-online.target

[Service]
WorkingDirectory=/opt/8kEdu
ExecStart=/opt/8kEdu/.venv/bin/python -m agent.curator --interval 600
Restart=always
User=%i

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kedu-serve kedu-api        # add kedu-curator to run the heartbeat
sudo systemctl status kedu-serve kedu-api --no-pager
```

Both apps auto-load `/opt/8kEdu/.env`, so no `EnvironmentFile` is needed.

---

## 7. nginx reverse proxy

`/etc/nginx/sites-available/8kedu` (replace `your.domain`):

```nginx
server {
    listen 80;
    server_name your.domain;
    root /opt/8kEdu/app/dist;

    # widget generation
    location /api/   { proxy_pass http://127.0.0.1:8756; }
    # dashboards + community
    location /agent/ { proxy_pass http://127.0.0.1:8787; }
    location /pub/   { proxy_pass http://127.0.0.1:8787; }

    # per-video pipeline output (concepts/transcript/chapters/frames), served from data/
    location ~ ^/[A-Za-z0-9_-]{11}/(concepts|transcript|chapters)\.json$ {
        root /opt/8kEdu/data;
    }
    location ~ ^/[A-Za-z0-9_-]{11}/frames/ {
        root /opt/8kEdu/data;
    }

    # SPA fallback (React Router-style: everything else → index.html)
    location / { try_files $uri $uri/ /index.html; }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/8kedu /etc/nginx/sites-enabled/8kedu
sudo nginx -t && sudo systemctl reload nginx
```

TLS: `sudo apt-get install -y certbot python3-certbot-nginx && sudo certbot --nginx -d your.domain`.

---

## 8. Add videos (the "drop a video" content)

The web UI's "drop a video" box opens videos that are **already analyzed**. Processing a
**new** YouTube video is a server-side CLI step (ingest + analyze on cloud inference):

```bash
cd /opt/8kEdu
.venv/bin/python ingest.py "https://www.youtube.com/watch?v=<VIDEO_ID>"
.venv/bin/python analyze.py --backend openrouter --video <VIDEO_ID>
```

Output lands in `data/<VIDEO_ID>/` and the Supabase cache; the video then works in the
app (open `https://your.domain/?v=<VIDEO_ID>`). To let judges process arbitrary videos
from the browser, wire a small `/api/ingest` endpoint that shells out to these two
commands — not built yet.

> **YouTube + datacenter IPs:** `yt-dlp` from a server IP can hit bot-checks. If a
> download 403s, pass browser cookies:
> `yt-dlp --cookies /opt/8kEdu/cookies.txt ...` (export cookies.txt from a logged-in
> browser), or run ingest from a residential machine and rsync `data/<id>/` up.

---

## 9. Smoke test

```bash
curl -s http://127.0.0.1:8756/api/info                      # {"backend":"openrouter",...}
curl -s http://127.0.0.1:8787/pub/config                    # {"url":...,"anon_key":...}
curl -s "http://127.0.0.1:8787/pub/feed?sort=hot" | head    # community feed
```

Then open `https://your.domain/` — landing, gallery, `?view=community`, `?view=agent`,
`?view=graph` should all load, and the live "ask → widget" flow should generate via
OpenRouter (watch `sudo journalctl -u kedu-serve -f`).

---

## Troubleshooting

- **`uv sync` tried to build mlx** → you're on macOS, or an old checkout. On Linux the
  `mlx-vlm` marker (`sys_platform == 'darwin'`) skips it; `git pull` to get it.
- **`cloud backend 'openrouter' is BLOCKED`** → set `KEDU_ALLOW_CLOUD=1` in `.env`.
- **Widget calls 401/insufficient credits** → check `OPENROUTER_API_KEY` and the
  learner's credit balance (`learners.credits`), or the user can add their own key in-app.
- **Empty dashboards** → `SUPABASE_DB_URL` wrong/unreachable; test with
  `psql "$SUPABASE_DB_URL" -c 'select 1'`.
- **Data files 404** → the nginx `root /opt/8kEdu/data` locations must point at the real
  repo `data/` dir; confirm `data/<id>/concepts.json` exists on disk.
