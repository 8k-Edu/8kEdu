---
name: refactor
description: Restructure existing code so its shape matches its responsibilities — SOLID seams, better names, encapsulation, the right mix of objects and plain functions — without changing behavior, then update the docs, prompts, and comments that referenced the old shape. Use this whenever someone says code is spaghetti, messy, tangled, duplicated, hard to follow, or has drifted through too many changes without landing, and whenever they ask to clean up, reorganize, split, rename, simplify, or "make this less awful" — a file, module, class, function, or a whole subsystem. Also use it when reviewing accumulated changes or a PR for design debt, even if nobody says the word "refactor", and whenever someone asks for the minimal, lazy, or shortest solution, invokes YAGNI, or complains about over-engineering, bloat, boilerplate, or unnecessary dependencies.
argument-hint: "[lite|full|ultra]"
license: MIT
compatibility: Reads `CLAUDE.md` and lint config for local rules. `scripts/clean-comments.sh` drives this repo's `.claude/hooks/comment-cleanup.sh`; it degrades to a hand pass where that hook is absent.
metadata:
  type: workflow
  owner: blend-ai
---

# Refactor

Refactoring is changing the shape of code without changing what it does. The
shape is worth changing when the code's structure no longer tells you the truth
about its responsibilities — when a reader has to hold five things in their head
to answer "where does X happen?"

Two failure modes bracket this work. Doing nothing leaves the mess. Doing too
much produces a different mess with a cleaner vocabulary: interfaces with one
implementation, factories for two branches, a class where a function was fine.
The job is to find the seams the code is already straining against and cut
along those, then stop.

## The ladder

Lazy means efficient, not careless. The best code is the code never written, and
a refactor's entire product is *less* — so before writing anything, climb until a
rung holds, then stop:

1. **Does this need to exist at all?** Speculative structure, a helper with one
   caller, a slice nobody asked for — skip it and say so in one line.
2. **Does it already exist here?** A helper, type, or pattern a few files over.
   Re-implementing what the codebase already has is the most common slop, and in
   a refactor it's the exact defect you were called in to remove.
3. **Does the stdlib do it?** Use it.
4. **Does a native platform feature cover it?** A DB constraint over app-layer
   checks, the framework's own hook over a hand-rolled one.
5. **Does an already-installed dependency solve it?** Use it. Never add a new
   one for what a few lines can do.
6. **Can it be one line?** One line.
7. **Only then:** the minimum code that works.

The ladder shortens the solution, never the reading. It runs *after* you
understand the problem — Steps 0–3 are not the part you skip, and laziness that
skips comprehension to ship a small diff is the dangerous kind, because it looks
like efficiency and lands a confident wrong fix. When two rungs both work, take
the higher one and move on; the first solution that holds is the right one. The
smallest change in the wrong place isn't lazy, it's a second bug.

## Intensity

`refactor lite|full|ultra` — default **full**, persists until changed.

| Level | What changes |
|-------|--------------|
| **lite** | Do the slices as asked, and name the lazier alternative in one line. The human picks. |
| **full** | The ladder enforced. Shortest diff that actually removes the defect. |
| **ultra** | Deletion before addition. Propose the one-slice version and question the rest of the request in the same breath. |

## Not this skill

- **Adding a feature or fixing a bug.** Do that separately. If the code must be
  restructured *to* fix the bug, do the restructure first as its own commit,
  confirm tests still pass, then fix.
- **Formatting/lint sweeps.** Run the formatter; that's not this.
- **A rewrite.** If the answer is "delete and start over", say so and stop —
  that's a design decision the human makes, not a refactor.

## Reviewing, not refactoring

When the target is someone else's PR or a pile of accumulated changes, you are
diagnosing, not cutting. Run Steps 0–3 — local rules, the territory, the
interface line, findings with evidence — and stop. Steps 4–7 assume you own the
change and don't apply.

Sort every finding into one of two buckets and say which it is:

- **Blocking** — a defect in the diff as written: wrong behavior, an `except`
  clause that can't fire, a test whose mock hides the thing it claims to prove.
- **Follow-up slice** — real design debt the diff worsens but didn't create:
  duplication it adds a copy to, a name it makes wronger.

Restructuring is never a merge condition on a behavioral change. Demanding it
produces exactly the mixed, unreviewable diff "Not this skill" warns against,
and it spends the credibility your blocking findings need. "Extract this before
a fifth caller arrives" lands; "restructure this PR" doesn't.

Do count the duplication a change *adds*, out loud — "this takes the clone
count from two to four" is concrete, and it's the argument for the follow-up.

## The contract: behavior does not move

Everything below depends on this. A refactor whose test results differ from the
baseline is not a refactor — it's an undocumented change, and the reviewer has
no way to tell which parts were intentional.

Before touching anything, capture a baseline:

```bash
pytest <scope> -q 2>&1 | tail -5          # record counts AND the failing set
<linter> <scope>                          # flake8 / ruff / eslint — record output
```

Save the numbers. After each slice, re-run and require **the same tests
passing** — not "tests pass". A green run with 4 fewer tests collected means you
deleted coverage. A newly-passing test means behavior moved.

If you find a genuine bug mid-refactor, write it down and keep going. Preserve
it faithfully, mention it in the report, and let the human decide. Silently
fixing it inside a "no behavior change" diff is how a refactor becomes
unreviewable.

## Step 0 — Load the local rules

Read `CLAUDE.md` / `AGENTS.md` (repo root and any nested ones on the path to
your target), plus lint config. Repo conventions outrank anything in this skill
or in general SOLID advice. Generic refactoring guidance will happily emit
`Optional[str]`, 120-char lines, or an extracted service class into a codebase
that forbids all three, and every one of those is a review comment.

Note specifically: line length, typing style, enum/StrEnum rules, import
placement, comment/docstring rules, and any architectural constraint about
where logic is allowed to live.

## Step 1 — Map the territory before judging it

Read the whole surface, not the diff. Then read how it got this way:

```bash
git log --oneline -30 -- <paths>
```

The log is the most under-used input in a refactor. Code that has been reworked
five times is code where each attempt was aiming somewhere, and the mess is
usually the residue of a *partially completed* migration rather than
carelessness. Find the direction of travel and finish that trip. A refactor that
introduces a sixth shape — even a tasteful one — makes the situation worse.

Also collect: every caller, every test, and every non-code reference (docs,
agent prompts, config, dashboards, SQL). You need these to size the blast
radius before you propose anything.

## Step 2 — Draw the interface line

Split the surface into two lists and keep them explicit. This is the single
highest-value five minutes in the whole workflow.

**Frozen** — renaming or re-shaping these changes behavior even when every unit
test stays green:
- Serialized/persisted field names, enum *values*, DB columns, API payloads.
- Anything an LLM reads: agent tool names, tool docstrings, prompt text,
  structured-output schema field names. These are inputs to a model, so a
  "clearer" name is a behavior change measurable only by evals.
- Public exports other repos/services import.

**Free** — invisible outside the module: private helpers, local variable names,
internal control flow, file organization within a package, duplicated logic,
class-vs-function choices for internals.

Refactor the free list freely. Frozen-list changes need a separate decision with
evidence (an eval run, a search of consumers), and belong in their own commit —
never mixed into a structural slice.

## Step 3 — Diagnose with evidence

Name concrete defects at `file:line`, not vibes. Each finding needs: what it is,
what it costs (the bug it invites, the change it makes expensive), and the move
that fixes it. Group findings so the human sees themes, not a list of 40 nits.

Read `references/design-moves.md` for the catalog — it maps each SOLID
principle to what it actually looks like in a modern codebase, plus naming
heuristics, encapsulation tells, and how to choose between an object, a
function, and a data structure. Read it during diagnosis, not after.

The findings that matter most, roughly in order:

1. **The same rule implemented in more than one place.** Especially arithmetic,
   parsing, and eligibility rules. This is the defect that actually produces
   incidents; two copies drift. Grep every caller before deciding where the fix
   belongs — one guard in the shared function is both the smaller diff and the
   root-cause fix, while patching the one path a ticket names leaves every
   sibling caller broken.
2. **A module that changes for unrelated reasons.** Split along the reasons.
3. **Names that lie or that need a comment to be understood.** A name that
   requires a comment explaining *what* is a naming bug.
4. **Leaked internals** — callers reaching into dicts/attributes to re-derive
   something the owner should expose as one call.
5. **Branching on type/kind in several places** — the same `if kind == ...`
   ladder repeated is asking for polymorphism or a dispatch table.
6. **Functions doing I/O and decisions together** — the reason they're hard to
   test.

## Step 4 — Propose slices, then get approval

Write the plan out and stop. Never open with a 900-line diff.

Each slice is: one intention, independently shippable, independently
verifiable, and small enough to review in one sitting. Order them so the risky
ones ride on top of already-verified ground. Label each `low / medium / high`
risk and say what verifies it.

Sequence that usually works:

1. Delete dead code (free, shrinks everything downstream).
2. Unify duplicated logic behind the one implementation that's already correct.
3. Extract and rename internals; tighten encapsulation.
4. Re-cut module boundaries.
5. Frozen-list renames — separately, last, with evidence.

Present the diagnosis and the slice list, then ask which slices to do. The human
may only want #1 and #2, and that's a complete outcome. Cutting scope is their
call.

## Step 5 — Apply one slice at a time

Per slice: make the change, re-run the baseline commands, compare against the
recorded numbers, then move on. Batching slices and verifying once at the end
means a failure tells you nothing about which change caused it.

Two habits that keep diffs reviewable:

- **Move or edit, not both.** A commit that relocates a function and rewrites it
  is unreviewable. Move it verbatim, verify, then edit in the next commit.
- **No drive-bys.** Every hunk in the diff should trace to a stated finding. If
  you notice something else, add it to the findings list for later.

If a slice turns out bigger than proposed, stop and re-check with the human
rather than expanding silently.

## Step 6 — Update everything that described the old shape

A refactor isn't done when the code compiles; it's done when nothing still
points at the shape you deleted. Search by the old symbol names for:

```bash
git grep -n "<old_name>" -- '*.md' '*.rst' '*.yaml' '*.yml' '*.json' '*.sql'
git grep -n "<old_name>"                                    # code + prompts
```

Cover: READMEs and `docs/`, module and class docstrings, agent prompts and tool
descriptions, config/fixture files, and architecture notes or ADRs describing
the layout you just changed. Stale docs are worse than none — they send the next
reader to a file that no longer exists.

Update `CLAUDE.md`/`AGENTS.md` only when the refactor establishes a convention
future work should follow ("income math lives in X; don't re-derive it"). Don't
log the refactor itself there — that's the PR description's job.

## Step 7 — Comment hygiene pass

Refactoring strands comments: step banners left over from extracted blocks,
comments describing code that moved, "this fixes..." notes addressed to a
long-gone reviewer.

If the repo ships a comment-cleanup hook, run it deliberately via the bundled
wrapper (it handles the details that make a bare invocation a silent no-op):

```bash
<skill-dir>/scripts/clean-comments.sh <files you changed>
```

The wrapper reports whether the cleanup actually modified anything — check that
output. Cleanup hooks commonly swallow errors and exit 0, so exit status alone
proves nothing. Expect it to be slow (it may spawn a nested model call); that's
not a hang.

No hook in the repo? Do the pass by hand against the repo's comment rules, and
apply the default that survives everywhere: comments explain **why**; delete
ones that narrate *what* the next line does, and delete or rewrite any comment
whose subject you just moved.

Then re-run the baseline verification one final time — cleanup passes edit
files, and edited files deserve a test run.

## Step 8 — Report

Give the human, briefly:

- What changed structurally, by slice.
- Verification: baseline vs. after (`182 passed` → `182 passed`, lint clean).
- Findings you deliberately left — bugs spotted, frozen-list renames declined,
  slices deferred — so nothing quietly disappears.
- Anything unit tests can't cover (prompt/eval surface, serialization).

This report was asked for, so give it in full. Prose *beyond* it is debt: if the
paragraph defending a slice runs longer than the slice, delete the paragraph.
Every argument for a simplification is complexity smuggled back in as prose.

## Restraint

Every move below is a real technique and a common way to make code worse. Reach
for one when the code is already straining against its current shape — three
call sites doing the same dance, a conditional ladder that's grown a third
branch — not because the pattern is recognizable.

- **An interface/ABC with one implementation.** Duck typing and a plain function
  already give you substitutability; the abstraction is pure indirection until a
  second implementation exists.
- **A factory for two options.** A dict or an `if` is clearer.
- **A class holding no state.** That's a module of functions with extra typing.
- **A dataclass wrapper around a dict you immediately unwrap.** Types earn their
  keep at boundaries that are crossed repeatedly, not at every hop.
- **Splitting a coherent 200-line module into six 30-line files.** Cohesion is
  the thing you're optimizing; file count isn't.
- **Renaming for taste on the frozen list.** See Step 2.
- **Deep inheritance to share a helper.** Compose or import.

The test for any proposed abstraction: can you name the *second* concrete case
it serves, today, in this repo? If not, leave the duplication and let the third
occurrence tell you the right shape.

Alongside those, the habits that keep a refactor from growing as it goes:

- **No scaffolding for later.** No boilerplate, no config for a value that never
  changes, no extension point with nothing to extend. Later can scaffold for
  itself.
- **Deletion over addition, boring over clever.** Clever is what the next person
  decodes at 3am while paged.
- **Fewest files that hold the shape.** File count isn't the thing being
  optimized; cohesion is.
- **Lazy about code, never about correctness.** Two options the same size? Take
  the one that's right on the edge cases. Writing less code doesn't license the
  flimsier algorithm.
- **Mark a deliberate corner.** A simplification with a known ceiling — a global
  lock, an O(n²) scan over a list you know stays short — gets one `TODO` naming
  the ceiling and the condition that retires it, following this repo's TODO
  rule rather than a new comment prefix.
- **Don't stall on a scope question you can default.** Ship the lazy slice and
  raise the larger version in the same breath: "did X; Y covers it — say the
  word if you want the full cut."

### When not to be lazy

Never simplify away input validation at a trust boundary, error handling that
prevents data loss, a security or authorization check, accessibility basics, or
anything explicitly requested. A refactor exposes these more than new work does:
they read like redundant defensive code, and deleting one is a behavior change
the baseline may not catch. Preserve them as-is, or make removing one its own
decision with evidence. If the human wants the fuller version after hearing the
lazy one, build it — no re-arguing.

Slices are verified by the baseline, not by new tests. The exception is a slice
that introduces genuinely new logic (a dispatch table, a parser, a money path):
leave behind the one smallest runnable check that fails if it breaks. No
fixtures, no per-function suite. YAGNI applies to tests too.

## Reference files

- `references/design-moves.md` — the diagnosis and move catalog: SOLID in
  practice, naming heuristics, encapsulation, choosing between objects,
  functions, and data. Read during Step 3.
- `scripts/clean-comments.sh` — invokes a repo's comment-cleanup hook correctly
  and reports what it actually changed. Used in Step 7.
