#!/usr/bin/env bash
#
# Delete-only comment hygiene pass. Spawns a Sonnet subagent that may only remove
# comment text — never write code, never author new comments. The rule set is CLAUDE.md's
# comment policy, enforced mechanically.
#
# Two entry points, one rule set:
#
#   1. Explicit file list (what the `refactor` skill calls):
#        .claude/hooks/comment-cleanup.sh serve.py agent/storage.py
#      Files are edited in place and left unstaged, so the caller can review the diff.
#
#   2. PreToolUse hook on `git commit`: reads the hook payload on stdin, cleans the
#      staged files and re-stages them so the commit picks the cleanup up. Note that
#      re-staging adds each file whole, so a partially staged file (`git add -p`) has
#      its remaining hunks swept into the commit as well.
#
# Always exits 0 — a missing `claude`, missing `jq` or a subagent failure must never
# block a real commit.

set -u

MODE="explicit"
files=()

if [ "$#" -gt 0 ]; then
  files=("$@")
else
  MODE="staged"
  command -v jq >/dev/null 2>&1 || exit 0
  payload=$(cat)
  cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""' 2>/dev/null || true)
  case "$cmd" in
    *"git commit"*) ;;
    *) exit 0 ;;
  esac
fi

command -v claude >/dev/null 2>&1 || exit 0

repo_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$repo_root" ] && [ -d "$repo_root" ] || exit 0
cd "$repo_root" || exit 0

if [ "$MODE" = "staged" ]; then
  while IFS= read -r f; do
    files+=("$f")
  done < <(git diff --cached --name-only --diff-filter=ACMR || true)
fi

[ ${#files[@]} -gt 0 ] || exit 0

# Source files only, and never generated, vendored or derived trees. `supabase/migrations/`
# is excluded on purpose: an applied migration is append-only history, so nothing edits it.
# `data/` is pipeline output, and `deploy/containment/` scripts are the security boundary —
# their comments are the audit trail.
keep=()
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  case "$f" in
    node_modules/*|*/node_modules/*|.venv/*|*/.venv/*|__pycache__/*) continue ;;
    data/*|app/dist/*|app/public/assets/*|docs/*|.claude/worktrees/*) continue ;;
    supabase/migrations/*|deploy/containment/*) continue ;;
    *.min.js|*.min.css|package-lock.json|uv.lock) continue ;;
  esac
  case "$f" in
    *.py|*.js|*.jsx|*.sql|*.sh) keep+=("$f") ;;
  esac
done
[ ${#keep[@]} -gt 0 ] || exit 0

read -r -d '' prompt <<'EOF' || true
Clean up comments in the listed files, applying CLAUDE.md's comment policy: let the code
speak for itself, and keep only what cannot be read from the code. This codebase documents
intent deliberately — most of its comments explain WHY a non-obvious choice was made, and
those are the most valuable prose in the repo. Your job is to remove the noise around them,
not to thin them out. When a comment is even arguably load-bearing, leave it.

Delete:
- Step-banner narration ("# Step 1: ...", "// ===== SECTION =====" dividers) — but NOT the
  `# ---------- named section ----------` markers described under Keep.
- Changelog and reviewer-addressed comments: "Previously...", "Updated to...",
  "This fixes...", "Per the plan...", "As requested...", "Renamed from...".
- Commented-out code (any commented line that would parse as code).
- Comments that contradict the code they sit next to — they went stale in a refactor.
- Comments that only restate WHAT the next line does when the line already says it
  ("# increment the counter" above `count += 1`).
- Docstring Args:/Returns: sections that only repeat the type hints. Leave the prose
  part of the docstring alone.

Keep:
- Section markers that name a region rather than restating a line. Two forms, both this
  repo's deliberate navigation idiom in files that run to hundreds or thousands of lines:
  `# ---------- named section ----------` in Python (agent/db.py, analyze.py, serve.py,
  agent/api.py) and short JSX markers like `{/* stat tiles */}` or `{/* HERO */}` in
  app/src/App.jsx. Never delete either, even when the file you are editing changed elsewhere.
- Anything explaining WHY: constraints, workarounds, third-party quirks (vllm/mlx/PIL/
  Supabase/Vite behaviour), ordering assumptions, perf tradeoffs, deliberate deviations
  from the obvious approach, rationale for a surprising default.
- Pointers to related code when the connection isn't visible locally ("see agent/db.py
  cache_get") — CLAUDE.md calls these out as worth keeping.
- Module, class and function docstrings.
- TODO/FIXME comments, shebangs, coding declarations, license headers, type-checker
  and linter directives (`# type: ignore`, `# noqa`, `// @ts-expect-error`,
  `// eslint-disable-*`).
- The `-- comment` lines in SQL that record why a grant, index or policy exists.

Hard constraints:
- Only DELETE comment lines or trim comment text. Never add a comment, never reword
  one, never change code, strings, imports, or whitespace on code lines.
- If unsure, leave it. A kept mediocre comment costs nothing; a deleted good one is
  lost work.
- Do not narrate. Do not summarize. Edit the files and finish.

Files:
EOF

printf '%s\n%s\n' "$prompt" "$(printf '%s\n' "${keep[@]}")" \
  | claude -p \
      --model sonnet \
      --allowed-tools "Edit,Read" \
      --dangerously-skip-permissions \
      >/dev/null 2>&1 || true

if [ "$MODE" = "staged" ]; then
  git add -- "${keep[@]}" >/dev/null 2>&1 || true
fi

exit 0
