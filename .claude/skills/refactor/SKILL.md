---
name: refactor
description: Behaviour-preserving SOLID refactor of the branch's own changes in 8kEdu, followed by a comment-hygiene pass and a docs refresh. Use this whenever the user asks to refactor, restructure, clean up, tidy, "apply SOLID", split a file that got too big, pull duplication out, separate concerns, or generally improve the shape of code without changing what it does — including phrasings like "clean this up before I open the PR", "this module is doing too much", "sort out the structure of the branch", or "refactor the diff from main". Also use it when someone asks to bring the docs back in line after moving code around. Prefer this skill over ad-hoc editing even for a single file, because it carries the repo's gate commands, its existing seams, and the anti-goals that stop a refactor from turning into a rewrite.
---

# Refactor (8kEdu)

A refactor here is a trade: you spend risk to buy clarity. This skill exists to keep the
risk small and the clarity real — the code must do exactly what it did before, every gate
that was green stays green, and the structure afterwards is easier to extend than the
structure before.

Four things must be true when you are done:

1. **Behaviour is unchanged.** No new features, no fixed bugs, no changed output. If you
   spot a genuine bug mid-refactor, note it and leave it — mixing a fix into a
   restructuring hides both.
2. **The gates are at least as green as the baseline you recorded.**
3. **Comments were cleaned** with `.claude/hooks/comment-cleanup.sh` over the files you
   touched.
4. **`README.md`'s architecture section and repository layout match the code** if module
   boundaries moved.

## Step 0 — Compute the scope

Refactor what this branch changed, not the whole repo. Untouched code is someone else's
decision and carries no review context.

```bash
BASE=$(git merge-base main HEAD)
git diff --name-only "$BASE"...HEAD -- \
  '*.py' 'agent/**' 'app/src/**' 'app/*.js' 'scripts/**' 'tests/**' \
  ':!data/**' ':!app/dist/**' ':!**/uv.lock' ':!app/package-lock.json' ':!supabase/migrations/**'
```

`origin/dev` and `main` are force-pushed in this repo, so a branch can orphan and
`merge-base` can point somewhere surprising. Sanity-check the file count before trusting
it: `dev` carries ~200 files against `main`, which is a release-sized diff, not a
refactorable slice. When the base is wrong or the user means "the work I just did", scope to
the uncommitted/session changes instead (`git status --porcelain`) and say which you chose.

If `main` has no shared history with `HEAD`, or the branch *is* `main`, fall back to the
tracked source tree and say so in your plan — an unbounded scope needs an explicit
decision, not a silent one.

Then measure before you commit to anything:

```bash
git diff --name-only "$BASE"...HEAD | wc -l
git ls-files '*.py' 'agent/*.py' 'app/src/*.jsx' | xargs wc -l | sort -rn | head -20
```

**Gate:** more than ~10 files or ~800 lines in play means you write a ranked plan first
and get it approved before editing. A refactor that touches everything at once cannot be
reviewed, and an unreviewable refactor is indistinguishable from a rewrite. If the user
has explicitly pre-authorised an unattended run, still write the plan — into the final
report — so the choices stay legible.

## Step 1 — Record the baseline

Run the gates *before* touching code. Without a recorded baseline, a red result afterwards
is uninterpretable — you cannot tell your refactor from a pre-existing failure.

Fast gates (run after every slice):

```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -q
uv run python -c "import serve, analyze, ingest, agent.api, agent.db, agent.storage"
cd app && npm run build
```

There is **no ruff, mypy, flake8 or ESLint config checked in**, and `pyproject.toml` has no
`[tool.*]` sections — do not invent a linter gate, and do not add one as part of a
refactor. The import check above is doing real work: `serve.py` imports `analyze` at module
scope and `agent/api.py` calls `db.load_env()` at import, so a broken import surfaces as a
startup failure rather than a test failure.

Slow gate (baseline once, then again before the final commit) — the app actually answering:

```bash
./run.sh && bash scripts/preflight.sh
curl -s -X POST http://127.0.0.1:8756/api/widget -H 'Content-Type: application/json' \
  -d '{"video":"5IgOP7Lpk5g","time":300,"text":"...","ask":"<unique string>"}'
```

Two things to know about coverage. `pytest` here is four-plus small unittest files with no
Supabase and no model — a green run proves the pure logic and the patched seams, nothing
about the live pipeline. And `preflight.sh` reports two ✗ on a perfectly healthy stack: it
greps `/v1/models` for `Nemotron` (the vllm-metal path serves `qwen3-vl-4b`) and it wants
`OPENROUTER_API_KEY`. Treat only the `:8756` / `:8787` / `:5174` / proxied-data lines as
signal, and say which gates you actually ran — over-claiming coverage is worse than
admitting the gap.

## Step 2 — SOLID, in this repo's idiom

SOLID is a diagnosis language, not a target architecture. Use it to name what hurts, then
apply the smallest change that removes the hurt.

**Single responsibility** — the live pressure here. `serve.py` is one file holding the
FastAPI routes, the two-tier widget cache, prompt hashing, Supabase auth, billing/credit
flow and the ingest subprocess driver. `analyze.py` holds the prompt, the schema, every
backend class, the backend factory, a dotenv loader and the batch runner. `app/src/App.jsx`
is several thousand lines of screen, chart and dashboard. The useful split is by *reason to
change* — a route changes when the API changes, a cache changes when the storage changes —
so those belong apart. Prefer moving a coherent group into a module next to its peers
(`agent/`) over inventing a new layer.

**Open/closed and dependency inversion** — respect the seams that already exist rather than
adding new ones. `analyze.make_backend()` is the abstraction the pipeline depends on and
`OpenAIBackend`/`MlxBackend` are the implementations behind it; every caller that names a
backend goes through `BACKEND_CHOICES`. When something endpoint-specific leaks into a
caller, move it behind the factory — that is a real DIP fix. Note the known violation:
`agent/brain.py` builds its own client outside `make_backend`, with its own env namespace
and no timeout. Folding it in is a legitimate refactor; adding a *second* factory beside it
is not.

**Interface segregation and Liskov** — `backend.ask(frame, context, max_px, system)` is the
contract, and `MlxBackend` needs a real filesystem path while `OpenAIBackend` only needs
bytes. Anything that narrows `ask` to bytes breaks the mlx implementation silently, since
`analyze.py` swallows per-frame exceptions. Check new backends honour the whole signature.

### Anti-goals

These are the failure modes that make refactors net-negative:

- **No abstraction with a single implementation.** An interface with one implementor is
  indirection you pay for and never use.
- **Additive, never replacing.** When touching backends, providers or serving paths, the
  existing option stays selectable. Do not repoint `KEDU_BACKEND`, collapse the
  `VLLM_*`/`NEMOTRON_*`/`KEDU_*` namespaces into one, or delete the LM Studio fallback
  because vllm is the current default.
- **No new dependencies.** The Python side is deliberately raw `psycopg2` + `urllib`
  (`agent/db_rest.py` exists specifically so the sandbox needs nothing extra installed),
  and `deploy/containment/Dockerfile.analyze` copies `analyze.py` alone and pip-installs
  only `openai` + `pillow`. A module-scope import of anything else in `analyze.py` kills
  every contained run.
- **No editing applied migrations.** `supabase/migrations/*.sql` is append-only history,
  and the remote ledger is already out of sync with the files. Schema changes are a new
  migration and a new feature — out of scope here.
- **No file explosion.** Splitting a 125-line module into six files makes it harder to
  read, not easier. Split when a file has two reasons to change, not when it crosses a line
  count.
- **No renaming across the public surface** (route paths, env var names, `BACKEND_CHOICES`
  values, table or column names, `PROMPT_VERSION`) unless you update every caller and the
  gates prove it. Renaming a cache key input silently invalidates the shared
  `inference_cache` for every user.
- **No behaviour "improvements" smuggled in.** Better error messages, extra validation and
  performance tweaks are separate commits.

## Step 3 — Execute in slices

One concern per slice: one module split, or one duplication removed, or one dependency
inverted. After each slice, run the fast gates and commit. Small commits are what make a
behaviour-preserving claim checkable — a reviewer can read one and believe it.

Prefer mechanical moves over rewrites. Moving a function to a new module with its imports
adjusted is verifiable by eye; re-expressing its logic on the way is not, and the two
should never share a commit.

If a slice turns out to need behaviour changes to work, stop that slice and record it as
follow-up work. The scope of a refactor shrinks; it does not grow.

## Step 4 — Comment hygiene

Refactoring strands comments: they describe code that moved, or narrate steps that no
longer exist. Run the cleaner over exactly the files you touched:

```bash
.claude/hooks/comment-cleanup.sh $(git diff --name-only "$BASE"...HEAD)
```

It is delete-only — it spawns a subagent that may remove comment text and nothing else —
and it enforces CLAUDE.md's policy while being biased toward keeping, because this repo's
comments are unusually good: they explain *why* (why `max_retries=0` on the model client,
why `VLLM_HOST_IP` is pinned to loopback, why the audio-tower transpose is a no-op, why the
storage fetch must not inherit `KEDU_TIMEOUT`). Losing those costs more than leaving a stale
one. Review its diff before committing; it is a tool, not an authority.

The same script is wired as a `PreToolUse` hook on `git commit` in `.claude/settings.json`,
where it cleans staged files and re-stages them. Calling it explicitly here means the
cleanup lands in the refactor's own commits with a visible diff rather than silently.

## Step 5 — Documentation

The doc set: **`README.md`** for what the project is, how to run it, the architecture
diagram and the repository-layout table; **`AGENTS.md`** and **`CLAUDE.md`** for the
conventions agents keep breaking (kept in sync with each other); **`docs/hackguide/`** for
the demo script and experiment notes. Do not add other top-level docs — a doc nobody is
required to read goes stale and then actively misleads.

README's Mermaid diagram and its `Repository layout` block answer "where does this code live
and what talks to what", at the level of modules and boundaries — never individual
functions, which change too often to keep true. Update them when a refactor moves a
boundary; leave them alone when nothing structural changed.

Also check README for claims your refactor invalidated — commands, file paths named in
prose, the env-var block, the stack list. Known drift to be careful not to propagate: README
says `localhost:5173` while the `dev` branch binds 5174 with `strictPort`, and it documents
quoted `.env` values while `agent/db.py`'s loader does not strip quotes.

## Step 6 — Verify and report

Rerun every gate, including the slow one you baselined. Then read your own diff
(`git diff --stat` plus the interesting hunks) as if reviewing someone else.

Report:

- What changed, grouped by concern, with the SOLID pressure each slice relieved.
- Gate results, before and after, naming which gates you actually ran.
- What you deliberately left alone and why — the ranked plan's tail, bugs you found and
  did not fix, follow-up work the scope rule pushed out.

A refactor report that lists only wins is not a report. The items you skipped are the ones
the reader needs most.
