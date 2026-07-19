# Spreadsheet widget for Excel / how-to lectures

**Date:** 2026-07-18
**Status:** approved design, pre-implementation
**Branch:** `worktree-excel-widget`

## Context

The 8kedu widget kit (`matrix_mul`, `attention`, `softmax`, `function_plot`, `notebook`,
`composite`) is tuned for STEM/math/finance. When we ran a Beginner-Excel lecture
(`5IgOP7Lpk5g`) through the live path, every moment fell through to a text **answer card** —
the VLM has no widget that fits a spreadsheet tutorial, so it emits `widget:"none"` + prose.

This spec adds a deterministic **`spreadsheet`** widget: an editable mini-Excel the learner
can type in, with a toolbar covering the beginner-Excel skills these videos teach. It follows
the kit's core principle — the model emits *data* (`params`), a deterministic component renders
it; no live codegen (the `notebook`/pyodide sandbox remains the only exception). The widget is
built as an **extensible template**: features live in a registry so new capabilities are a
one-entry change.

## Goals

- A reusable editable spreadsheet widget covering: **alignment** (L/C/R, wrap, merge & center,
  orientation, shrink-to-fit), **text formatting** (bold, italic, underline, fill, font color),
  **number format** (currency, %, decimals), **formulas** (`SUM/AVERAGE/MIN/MAX/COUNT`, refs,
  ranges, arithmetic).
- The VLM seeds the grid from the teacher's frame and spotlights the features that moment teaches;
  the learner still has the full toolbar (free sandbox).
- Genre-aware prompting wired into the **live** `serve.py` path, non-mutating.
- No regression to existing widgets; no new runtime-security surface.

## Non-goals (YAGNI, room to grow via the registry)

- Absolute refs (`$A$1`), nested/other spreadsheet functions, string functions.
- Multi-sheet, charts, cell borders, copy/paste fill, undo history.
- Arbitrary on-the-fly JS/HTML component generation (rejected: fights the deterministic-kit
  architecture; the `notebook` widget already covers the "generated code, safely sandboxed" case).

## Architecture

```
frame + transcript ─▶ VLM (genre: spreadsheet) ─▶ spec {widget:"spreadsheet", params:{cells,features,highlight}}
                                                        │
                             analyze.py valid() gate ───┤
                                                        ▼
                          App.jsx  WIDGETS["spreadsheet"] ─▶ <Spreadsheet params onState/>
                                                        │
                                    editable grid + toolbar (FEATURES registry)
                                    formula evaluator (pure JS)
                                    onState ─▶ remix / QR encode (same as other widgets)
```

### Component — `Spreadsheet({ params, onState })` in `app/src/widgets.jsx`

- **State:** `grid` = 2D array of `{ value, style }`; `style` = `{bold, italic, underline, align,
  wrap, shrink, orient, numFmt, fill, color, merged}`. Seeded from `params.cells` (values) with
  empty styles. Column headers A/B/C…, row numbers 1..N, Excel-style.
- **Editing:** click a cell → edit its `value`. A value starting with `=` is a formula.
- **Toolbar:** buttons grouped Alignment / Text / Number / Formula. Each button applies its
  effect to the selected cell(s). `params.features` (if present) visually spotlights the relevant
  group; all groups remain usable.
- **`highlight`:** optional single `{row,col}` drawn with a ring to point the learner at the
  moment's cell (range highlight is a non-goal for MVP).
- **Live state:** `useEffect(() => onState?.({ ...params, grid }))` — mirrors the existing widgets
  so URL/QR remix keeps working.

### Feature registry — the "template" extension point

```js
const FEATURES = [
  { id:'align_left',   group:'align',  label:'⯇', apply:(s)=>({...s, align:'left'}) },
  { id:'wrap',         group:'align',  label:'wrap', apply:(s)=>({...s, wrap:!s.wrap}) },
  { id:'merge_center', group:'align',  label:'merge', apply:(s,ctx)=>ctx.mergeSelection() },
  { id:'orientation',  group:'align',  label:'⤡', apply:(s)=>({...s, orient:(s.orient?0:90)}) },
  { id:'bold',         group:'text',   label:'B', apply:(s)=>({...s, bold:!s.bold}) },
  { id:'currency',     group:'number', label:'$', apply:(s)=>({...s, numFmt:'currency'}) },
  // …one entry per capability; adding a feature = add an entry (+ its render if structural)
]
```

Most features are pure `style` toggles (trivial). Structural ones (merge) get a `ctx` with grid
ops. Rendering reads `style` → CSS (`text-align`, `white-space:pre-wrap`, `writing-mode`/`rotate`,
`font-weight`, number formatting).

### Formula evaluator — pure JS, self-contained, no dependency

- `evalFormula(src, grid)`: parse `=…`, resolve cell refs (`A1`→`grid[0][0].value`) and ranges
  (`A1:A3`→ array), support `SUM/AVERAGE/MIN/MAX/COUNT(range|args)` and `+ - * / ( )`.
- Tokenize → shunting-yard → evaluate, or a guarded recursive-descent parser. **No `eval()`** on
  user input — a real tiny parser (refs + numbers + ops + the 5 funcs only).
- Recompute displayed values on every edit; a cell's stored `value` keeps the `=…` source,
  display shows the computed result. Ref cycles → show `#CYCLE`, bad refs → `#REF!`.

### Spec / params (what the VLM emits)

```json
{ "has_concept": true, "widget": "spreadsheet",
  "title": "Wrap long headers", "explanation": "why it matters (one sentence)",
  "params": {
    "cells": [["Month number","Sales"],["Jan",100],["Feb",140]],
    "features": ["wrap","merge_center","orientation"],
    "highlight": {"row":0,"col":0}
  } }
```

`cells` required (non-empty 2D of strings/numbers). `features` optional (subset of registry ids;
default = all). `highlight` optional.

### analyze.py changes

- `CONCEPT_SCHEMA.enum` (line ~28): add `"spreadsheet"`; add `params` props `cells` (2D array),
  `features` (array of strings), `highlight` (object).
- `ALLOWED`: add `"spreadsheet"`.
- `valid()` (line ~181): branch — `cells` is a non-empty list of non-empty lists.
- `SYSTEM` widget list (line ~94) + the widget menu (lines 66–86): add a `spreadsheet` line
  ("a spreadsheet/Excel screen is shown → params {cells, features, highlight}").

### Genre wiring (folds in Task 8)

- New genre **`spreadsheet`** in `GENRE_PROMPTS`: "This is a spreadsheet/Excel tutorial. Emit a
  `spreadsheet` widget — `cells` = the grid on screen (headers + a few real rows), `features` =
  the alignment/format/formula actions this moment teaches. The learner gets an editable grid to
  try it." Add `GENRE_KEYWORDS.spreadsheet = [excel, spreadsheet, cell, column, row, formula,
  workbook, sheet, worksheet, ribbon]`.
- **Non-mutating live path:** `apply_genre` currently mutates the module global `SYSTEM` — unsafe
  in a long-running server (genre leaks across requests). Add `system_for(genre) -> str` that
  *returns* the composed prompt, and thread an optional `system=` param through
  `MlxBackend.ask` / `OpenAIBackend.ask` (default = base `SYSTEM`). Refactor `apply_genre` to
  delegate to `system_for` (offline CLI keeps current behavior via the returned string).
- `serve.py`: on `/api/widget` and `/api/region`, resolve genre — prefer `videos.genre`
  (new `db.video_genre(video_id)` helper, one indexed read; cache in `_frames_cache`-style dict),
  fall back to `detect_genre` over the passage, else base prompt — and pass `system=system_for(g)`
  into `backend.ask`. NULL genre → base prompt (no regression).

## File-by-file

| File | Change |
|---|---|
| `app/src/widgets.jsx` | `Spreadsheet` component + `FEATURES` registry + formula evaluator; add to `WIDGETS`. |
| `analyze.py` | schema enum/props, `ALLOWED`, `valid()` branch, SYSTEM widget line, `GENRE_PROMPTS`/`GENRE_KEYWORDS` `spreadsheet`, `system_for()`, `ask(system=)`. |
| `serve.py` | genre resolve + `system=` on both endpoints; bump `PROMPT_VERSION` (new prompt → fresh cache keys). |
| `agent/db.py` | `video_genre(video_id)` helper. |
| `app/src/App.jsx` | render path already generic via `WIDGETS[...]`; verify the spreadsheet card sizing. |

## Testing / verification

1. **Unit (formula):** a tiny node script or inline checks — `=SUM(A1:A3)`, `=A1*2`,
   `=AVERAGE(A1:B2)`, cycle, bad ref.
2. **Widget render:** `npm run build`; load a hand-written `spreadsheet` spec in the UI, exercise
   each toolbar group + a formula; confirm `onState` round-trips (remix URL reopens same state).
3. **End-to-end (Task 10):** set `videos.genre='spreadsheet'` for `5IgOP7Lpk5g`; live-ask a few
   moments → expect `spreadsheet` widgets (not answer cards); check `?view=perf` still < 5 s.
4. **No regression:** the 4 pre-baked videos still mint their usual widgets; base prompt unchanged
   when genre is NULL/general.

## Risks

- **VLM emits malformed `cells`** → `valid()` rejects → falls back to answer card (graceful).
- **512/768px readability** for reading grid values → tune `TACTILE_MAX_PX`; the widget seeds from
  whatever the VLM reads, learner can correct in-grid.
- **Formula parser scope creep** → registry + non-goals keep it bounded.
