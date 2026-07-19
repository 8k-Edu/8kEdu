# Spreadsheet Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, editable `spreadsheet` widget so Excel/how-to lecture moments mint an interactive grid instead of a text answer card.

**Architecture:** The VLM emits `params:{cells,features,highlight}`; a React `<Spreadsheet>` renders an editable grid + toolbar (features come from an extensible registry); a pure-JS evaluator computes formulas. A new `spreadsheet` genre steers the prompt, wired into the live `serve.py` path via a non-mutating `system_for(genre)`.

**Tech Stack:** React 18 (no new deps), pure-JS formula evaluator, FastAPI (`serve.py`), Python (`analyze.py`, `agent/db.py`), Supabase Postgres. Tests: Node ≥22 built-in `node --test` (JS), plain `assert` scripts (Python).

## Global Constraints

- Node ≥ 22.19, Python 3.12, run everything from the worktree root `/Users/nscipione/Developer/Personal/8kedu/.claude/worktrees/excel-widget`.
- No new npm or python dependencies. React components take `({ params, onState })` and report live state via `onState?.(...)` in a `useEffect` (match existing widgets in `app/src/widgets.jsx`).
- `app/` is ESM (`"type":"module"`). Python run via `uv run` / `.venv` (symlinked).
- Deterministic kit: the model emits data, components render it. No `eval()` on user input.
- Commit after each task with a `feat:`/`test:` message.

---

### Task 1: Formula evaluator (pure JS, TDD)

**Files:**
- Create: `app/src/formula.js`
- Test: `app/src/formula.test.js`

**Interfaces:**
- Produces: `evalFormula(src: string, grid: Cell[][], seen?: Set<string>) -> number | string`, where `Cell` is `{value, style}` or a bare value. Returns a number for computed formulas, the raw value for non-formulas, `'#REF!'` / `'#CYCLE'` on error.

- [ ] **Step 1: Write the failing test**

Create `app/src/formula.test.js`:
```js
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evalFormula } from './formula.js'

const g = (rows) => rows.map(r => r.map(v => ({ value: v, style: {} })))

test('plain number passes through', () => {
  assert.equal(evalFormula('42', g([['42']])), 42)
})
test('non-formula string passes through', () => {
  assert.equal(evalFormula('Jan', g([['Jan']])), 'Jan')
})
test('arithmetic with precedence and parens', () => {
  assert.equal(evalFormula('=2+3*4', g([[]])), 14)
  assert.equal(evalFormula('=(2+3)*4', g([[]])), 20)
  assert.equal(evalFormula('=-5+2', g([[]])), -3)
})
test('cell ref', () => {
  assert.equal(evalFormula('=A1*2', g([[10]])), 20)
})
test('SUM over a range', () => {
  assert.equal(evalFormula('=SUM(A1:A3)', g([[10],[20],[30]])), 60)
})
test('AVERAGE / MIN / MAX / COUNT', () => {
  const grid = g([[10],[20],[30]])
  assert.equal(evalFormula('=AVERAGE(A1:A3)', grid), 20)
  assert.equal(evalFormula('=MIN(A1:A3)', grid), 10)
  assert.equal(evalFormula('=MAX(A1:A3)', grid), 30)
  assert.equal(evalFormula('=COUNT(A1:A3)', grid), 3)
})
test('nested formula reference resolves', () => {
  // A1=5, A2==A1*2, B1==A2+1  → 11
  assert.equal(evalFormula('=A2+1', g([[5, '=A1*2'], ['=A1*2']])), 11)
})
test('bad ref returns #REF!', () => {
  assert.equal(evalFormula('=ZZ99+1', g([[1]])), '#REF!')
})
test('cycle returns #CYCLE', () => {
  // A1==B1, B1==A1
  const grid = g([['=B1', '=A1']])
  assert.equal(evalFormula('=A1', grid), '#CYCLE')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && node --test src/formula.test.js`
Expected: FAIL — `Cannot find module './formula.js'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/src/formula.js`:
```js
// Tiny spreadsheet formula evaluator: cell refs (A1), ranges (A1:A3),
// SUM/AVERAGE/MIN/MAX/COUNT, and + - * / ( ) with unary minus. No eval().
const FUNCS = {
  SUM: (a) => a.reduce((s, x) => s + x, 0),
  AVERAGE: (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0),
  MIN: (a) => (a.length ? Math.min(...a) : 0),
  MAX: (a) => (a.length ? Math.max(...a) : 0),
  COUNT: (a) => a.length,
}

const colToIndex = (s) => {
  let n = 0
  for (const ch of s) n = n * 26 + (ch.charCodeAt(0) - 64)
  return n - 1
}
const refToRC = (ref) => {
  const m = /^([A-Z]+)([0-9]+)$/.exec(ref)
  if (!m) return null
  return { r: parseInt(m[2], 10) - 1, c: colToIndex(m[1]) }
}
const rawAt = (grid, r, c) => {
  const cell = grid[r] && grid[r][c]
  if (cell == null) return null
  return typeof cell === 'object' ? cell.value : cell
}

function cellNumber(ref, grid, seen) {
  const rc = refToRC(ref)
  if (!rc || rc.r < 0 || rc.c < 0 || rc.r >= grid.length) throw new Error('REF')
  const key = rc.r + ',' + rc.c
  if (seen.has(key)) throw new Error('CYCLE')
  const raw = rawAt(grid, rc.r, rc.c)
  if (raw == null || raw === '') return 0
  if (typeof raw === 'string' && raw.startsWith('=')) {
    const s2 = new Set(seen); s2.add(key)
    const v = evalExpr(tokenize(raw.slice(1)), { i: 0 }, grid, s2)
    if (typeof v !== 'number') throw new Error('REF')
    return v
  }
  const n = Number(raw)
  if (Number.isNaN(n)) throw new Error('REF')
  return n
}

function rangeValues(a, b, grid, seen) {
  const ra = refToRC(a), rb = refToRC(b)
  if (!ra || !rb) throw new Error('REF')
  const out = []
  for (let r = Math.min(ra.r, rb.r); r <= Math.max(ra.r, rb.r); r++)
    for (let c = Math.min(ra.c, rb.c); c <= Math.max(ra.c, rb.c); c++) {
      const raw = rawAt(grid, r, c)
      if (raw == null || raw === '') continue
      out.push(cellNumber(colName(c) + (r + 1), grid, seen))
    }
  return out
}
const colName = (c) => {
  let s = '', n = c + 1
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26) }
  return s
}

function tokenize(src) {
  const toks = []
  const re = /\s*([A-Z]+[0-9]+|[A-Z]+|[0-9]*\.?[0-9]+|[()+\-*/,:])/gy
  let m
  while ((m = re.exec(src))) toks.push(m[1])
  return toks
}

// recursive descent: expr := term (('+'|'-') term)* ; term := factor (('*'|'/') factor)*
function evalExpr(toks, pos, grid, seen) {
  let v = evalTerm(toks, pos, grid, seen)
  while (toks[pos.i] === '+' || toks[pos.i] === '-') {
    const op = toks[pos.i++]
    const rhs = evalTerm(toks, pos, grid, seen)
    v = op === '+' ? v + rhs : v - rhs
  }
  return v
}
function evalTerm(toks, pos, grid, seen) {
  let v = evalFactor(toks, pos, grid, seen)
  while (toks[pos.i] === '*' || toks[pos.i] === '/') {
    const op = toks[pos.i++]
    const rhs = evalFactor(toks, pos, grid, seen)
    v = op === '*' ? v * rhs : v / rhs
  }
  return v
}
function evalFactor(toks, pos, grid, seen) {
  const t = toks[pos.i]
  if (t === '-') { pos.i++; return -evalFactor(toks, pos, grid, seen) }
  if (t === '(') { pos.i++; const v = evalExpr(toks, pos, grid, seen); pos.i++; return v }
  if (t in FUNCS) {
    pos.i++            // func name
    pos.i++            // '('
    const args = []
    while (toks[pos.i] !== ')') {
      if (/^[A-Z]+[0-9]+$/.test(toks[pos.i]) && toks[pos.i + 1] === ':') {
        const a = toks[pos.i]; pos.i += 2; const b = toks[pos.i++]
        args.push(...rangeValues(a, b, grid, seen))
      } else {
        args.push(evalExpr(toks, pos, grid, seen))
      }
      if (toks[pos.i] === ',') pos.i++
    }
    pos.i++            // ')'
    return FUNCS[t](args)
  }
  if (/^[A-Z]+[0-9]+$/.test(t)) { pos.i++; return cellNumber(t, grid, seen) }
  if (t !== undefined && !Number.isNaN(Number(t))) { pos.i++; return Number(t) }
  throw new Error('REF')
}

export function evalFormula(src, grid, seen = new Set()) {
  if (typeof src !== 'string' || !src.startsWith('=')) {
    const n = Number(src)
    return src !== '' && !Number.isNaN(n) ? n : src
  }
  try {
    const v = evalExpr(tokenize(src.slice(1)), { i: 0 }, grid, seen)
    return typeof v === 'number' && Number.isFinite(v) ? v : '#REF!'
  } catch (e) {
    return e.message === 'CYCLE' ? '#CYCLE' : '#REF!'
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && node --test src/formula.test.js`
Expected: PASS — all tests pass, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add app/src/formula.js app/src/formula.test.js
git commit -m "feat: pure-JS spreadsheet formula evaluator + tests"
```

---

### Task 2: Spreadsheet widget component

**Files:**
- Modify: `app/src/widgets.jsx` (add `Spreadsheet`, import `evalFormula`, register in `WIDGETS`)

**Interfaces:**
- Consumes: `evalFormula` from `./formula.js` (Task 1).
- Produces: `Spreadsheet({ params, onState })` and `WIDGETS.spreadsheet`. `params` shape: `{ cells: (string|number)[][], features?: string[], highlight?: {row,col} }`.

- [ ] **Step 1: Import the evaluator and add the component**

At the top of `app/src/widgets.jsx`, add to the existing imports:
```js
import { evalFormula } from './formula.js'
```

Add this component (place it just before `export const WIDGETS = {`):
```jsx
const SS_FEATURES = [
  { id: 'align_left',   group: 'Align',  label: '⯇',    apply: s => ({ ...s, align: 'left' }) },
  { id: 'align_center', group: 'Align',  label: '≡',    apply: s => ({ ...s, align: 'center' }) },
  { id: 'align_right',  group: 'Align',  label: '⯈',    apply: s => ({ ...s, align: 'right' }) },
  { id: 'wrap',         group: 'Align',  label: 'wrap', apply: s => ({ ...s, wrap: !s.wrap }) },
  { id: 'shrink',       group: 'Align',  label: 'shrink', apply: s => ({ ...s, shrink: !s.shrink }) },
  { id: 'orientation',  group: 'Align',  label: '⤡',    apply: s => ({ ...s, orient: s.orient ? 0 : 90 }) },
  { id: 'merge_center', group: 'Align',  label: 'merge', structural: true },
  { id: 'bold',         group: 'Text',   label: 'B',    apply: s => ({ ...s, bold: !s.bold }) },
  { id: 'italic',       group: 'Text',   label: 'I',    apply: s => ({ ...s, italic: !s.italic }) },
  { id: 'underline',    group: 'Text',   label: 'U',    apply: s => ({ ...s, underline: !s.underline }) },
  { id: 'fill',         group: 'Text',   label: '🖌',    apply: s => ({ ...s, fill: s.fill ? null : '#fff3b0' }) },
  { id: 'currency',     group: 'Number', label: '$',    apply: s => ({ ...s, numFmt: s.numFmt === 'currency' ? null : 'currency' }) },
  { id: 'percent',      group: 'Number', label: '%',    apply: s => ({ ...s, numFmt: s.numFmt === 'percent' ? null : 'percent' }) },
  { id: 'decimals',     group: 'Number', label: '.00',  apply: s => ({ ...s, decimals: ((s.decimals ?? 0) + 1) % 4 }) },
]
const SS_BY_ID = Object.fromEntries(SS_FEATURES.map(f => [f.id, f]))
const colName = (c) => { let s = '', n = c + 1; while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26) } return s }

function fmtDisplay(raw, grid, style) {
  let v = (typeof raw === 'string' && raw.startsWith('=')) ? evalFormula(raw, grid) : raw
  if (typeof v === 'number') {
    const d = style.decimals ?? (style.numFmt ? 2 : undefined)
    if (style.numFmt === 'currency') return '$' + v.toLocaleString(undefined, { minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2 })
    if (style.numFmt === 'percent') return (v * 100).toFixed(d ?? 0) + '%'
    if (d != null) return v.toFixed(d)
  }
  return v ?? ''
}

export function Spreadsheet({ params, onState }) {
  const seed = (params.cells && params.cells.length ? params.cells : [['']]).map(
    row => row.map(v => ({ value: v == null ? '' : String(v), style: {} }))
  )
  const cols = Math.max(...seed.map(r => r.length), 3)
  const norm = seed.map(r => { const c = r.slice(); while (c.length < cols) c.push({ value: '', style: {} }); return c })
  const [grid, setGrid] = useState(norm)
  const [sel, setSel] = useState({ r: 0, c: 0 })
  const spotlight = new Set(params.features ?? [])
  const hi = params.highlight

  useEffect(() => { onState?.({ ...params, cells: grid.map(r => r.map(c => c.value)) }) }, [grid]) // eslint-disable-line

  const rawGrid = grid.map(r => r.map(c => ({ value: c.value, style: c.style })))
  const setCell = (r, c, patch) => setGrid(g => g.map((row, ri) => row.map((cell, ci) =>
    ri === r && ci === c ? { ...cell, ...patch } : cell)))
  const applyFeature = (f) => {
    if (f.structural) return
    setCell(sel.r, sel.c, { style: f.apply(grid[sel.r][sel.c].style) })
  }
  const groups = ['Align', 'Text', 'Number']

  return (
    <div style={{ ...card }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        {groups.map(gr => (
          <div key={gr} style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#8b949e', marginRight: 2 }}>{gr}</span>
            {SS_FEATURES.filter(f => f.group === gr).map(f => (
              <button key={f.id} onClick={() => applyFeature(f)} title={f.id}
                style={{
                  fontSize: 12, minWidth: 26, height: 24, cursor: 'pointer',
                  border: `1px solid ${spotlight.has(f.id) ? '#e3b341' : '#30363d'}`,
                  background: spotlight.has(f.id) ? '#e3b34122' : '#161b22', color: '#e6edf3',
                  fontWeight: f.id === 'bold' ? 800 : 500, borderRadius: 5,
                }}>{f.label}</button>
            ))}
          </div>
        ))}
      </div>
      <div style={{ overflow: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={ssHead}></th>
              {grid[0].map((_, c) => <th key={c} style={ssHead}>{colName(c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {grid.map((row, r) => (
              <tr key={r}>
                <td style={ssHead}>{r + 1}</td>
                {row.map((cell, c) => {
                  const st = cell.style
                  const isHi = hi && hi.row === r && hi.col === c
                  const isSel = sel.r === r && sel.c === c
                  return (
                    <td key={c} onClick={() => setSel({ r, c })}
                      style={{
                        border: `1px solid ${isSel ? '#388bfd' : '#30363d'}`,
                        outline: isHi ? '2px solid #e3b341' : 'none',
                        minWidth: 70, maxWidth: st.wrap ? 90 : 220, height: 26, padding: '2px 6px',
                        textAlign: st.align || (typeof cell.value === 'number' ? 'right' : 'left'),
                        fontWeight: st.bold ? 700 : 400, fontStyle: st.italic ? 'italic' : 'normal',
                        textDecoration: st.underline ? 'underline' : 'none',
                        whiteSpace: st.wrap ? 'normal' : 'nowrap', overflow: 'hidden',
                        background: st.fill || 'transparent',
                        writingMode: st.orient ? 'vertical-rl' : 'horizontal-tb',
                      }}>
                      <input value={cell.value}
                        onChange={e => setCell(r, c, { value: e.target.value })}
                        onFocus={() => setSel({ r, c })}
                        style={{
                          width: '100%', border: 'none', background: 'transparent', color: '#e6edf3',
                          font: 'inherit', textAlign: 'inherit', outline: 'none',
                          display: (document.activeElement && isSel) ? undefined : 'none',
                        }} />
                      <span style={{ display: isSel ? 'none' : 'inline' }}>
                        {fmtDisplay(cell.value, rawGrid, st)}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
        <button onClick={() => setGrid(g => [...g, g[0].map(() => ({ value: '', style: {} }))])}
          style={ssAddBtn}>＋ row</button>
        <button onClick={() => setGrid(g => g.map(row => [...row, { value: '', style: {} }]))}
          style={ssAddBtn}>＋ col</button>
      </div>
    </div>
  )
}
const ssHead = { border: '1px solid #30363d', background: '#161b22', color: '#8b949e', fontSize: 11, padding: '2px 6px', textAlign: 'center' }
const ssAddBtn = { fontSize: 11, padding: '3px 9px', border: '1px solid #30363d', background: '#161b22', color: '#8b949e', borderRadius: 5, cursor: 'pointer' }
```

Note: the merge_center feature is registered as `structural` with no `apply` yet — it is a visible (spotlightable) no-op for this task. Wiring the range-merge behavior is Task 2b.

- [ ] **Step 2: Register in the WIDGETS map**

Modify `app/src/widgets.jsx` — the `WIDGETS` object:
```js
export const WIDGETS = {
  matrix_mul: MatrixMul,
  attention: Attention,
  softmax: Softmax,
  function_plot: FunctionPlot,
  composite: Composite,
  notebook: Notebook,
  spreadsheet: Spreadsheet,
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd app && npx --no-install vite build`
Expected: `✓ built` with no errors.

- [ ] **Step 4: Manual render check**

Run: `cd .. && ./run.sh` then open `http://localhost:5173/?view=learn` is not needed — instead verify directly: `cd app && npm run dev`, open the app, and in the browser console run:
```js
// quick smoke: mount a spreadsheet spec via the existing selected-widget path is app-specific;
// simplest check — confirm the module exports and evaluator wire up:
```
Concretely: create `app/src/spreadsheet.demo.jsx` importing `Spreadsheet` and rendering `<Spreadsheet params={{cells:[['Month','Sales'],['Jan',100],['Feb',140],['Total','=SUM(B2:B3)']],features:['wrap','merge_center']}} />` at the app root temporarily, `npm run dev`, confirm: grid renders, typing in a cell works, `=SUM(B2:B3)` shows `240`, the `wrap`/`merge` buttons show gold spotlight. Then delete `spreadsheet.demo.jsx`.

- [ ] **Step 5: Commit**

```bash
git add app/src/widgets.jsx
git commit -m "feat: editable Spreadsheet widget with feature-registry toolbar"
```

---

### Task 2b: Merge & center behavior

**Files:**
- Modify: `app/src/widgets.jsx` (`Spreadsheet` — range selection + merge render)

**Interfaces:**
- Consumes: `Spreadsheet` state from Task 2.
- Produces: merge behavior on `merge_center`; merged anchor cell stores `style.merged = {rows, cols}`, covered cells store `style.covered = true`.

- [ ] **Step 1: Add range selection**

In `Spreadsheet`, replace the single `sel` with an anchor+focus range. Add:
```js
const [range, setRange] = useState(null) // {r0,c0,r1,c1} or null
const inRange = (r, c) => range && r >= Math.min(range.r0, range.r1) && r <= Math.max(range.r0, range.r1)
  && c >= Math.min(range.c0, range.c1) && c <= Math.max(range.c0, range.c1)
```
On cell `onMouseDown`: `setRange({r0:r,c0:c,r1:r,c1:c}); setSel({r,c})`. On cell `onMouseEnter` while mouse is down (track with a `dragging` ref): `setRange(rg => rg && {...rg, r1:r, c1:c})`.

- [ ] **Step 2: Implement merge on the feature**

Replace `applyFeature` so `merge_center` collapses the current range:
```js
const applyFeature = (f) => {
  if (f.id === 'merge_center') {
    if (!range) return
    const r0 = Math.min(range.r0, range.r1), c0 = Math.min(range.c0, range.c1)
    const r1 = Math.max(range.r0, range.r1), c1 = Math.max(range.c0, range.c1)
    setGrid(g => g.map((row, ri) => row.map((cell, ci) => {
      if (ri === r0 && ci === c0) return { ...cell, style: { ...cell.style, align: 'center', merged: { rows: r1 - r0 + 1, cols: c1 - c0 + 1 }, covered: false } }
      if (ri >= r0 && ri <= r1 && ci >= c0 && ci <= c1) return { ...cell, style: { ...cell.style, covered: true } }
      return cell
    })))
    return
  }
  if (!f.structural) setCell(sel.r, sel.c, { style: f.apply(grid[sel.r][sel.c].style) })
}
```

- [ ] **Step 3: Render merged cells**

In the cell render: if `st.covered` return `null` (skip the `<td>`); if `st.merged` add `colSpan={st.merged.cols} rowSpan={st.merged.rows}`.

- [ ] **Step 4: Verify build + manual**

Run: `cd app && npx --no-install vite build` → `✓ built`.
Manual (reuse the demo from Task 2 Step 4): drag-select B2:B3, click `merge` → the two cells become one centered cell.

- [ ] **Step 5: Commit**

```bash
git add app/src/widgets.jsx
git commit -m "feat: merge & center via drag-selected range in Spreadsheet"
```

---

### Task 3: Backend schema + validation for `spreadsheet`

**Files:**
- Modify: `analyze.py` (CONCEPT_SCHEMA, ALLOWED, valid(), SYSTEM)
- Test: `tests/test_valid_spreadsheet.py`

**Interfaces:**
- Consumes: existing `valid(spec)` in `analyze.py`.
- Produces: `valid()` accepts a well-formed `spreadsheet` spec, rejects malformed `cells`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_valid_spreadsheet.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from analyze import valid

good = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
        "params": {"cells": [["Month", "Sales"], ["Jan", 100]]}}
assert valid(good), "well-formed spreadsheet spec should be valid"

no_cells = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
            "params": {"features": ["wrap"]}}
assert not valid(no_cells), "missing cells should be invalid"

empty = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
         "params": {"cells": []}}
assert not valid(empty), "empty cells should be invalid"

print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/test_valid_spreadsheet.py`
Expected: FAIL — `AssertionError: well-formed spreadsheet spec should be valid` (widget not in ALLOWED yet).

- [ ] **Step 3: Implement schema + validation**

In `analyze.py`:
1. CONCEPT_SCHEMA `widget.enum` — add `"spreadsheet"`:
```python
"enum": ["matrix_mul", "attention", "softmax", "function_plot", "notebook", "spreadsheet", "none"],
```
2. CONCEPT_SCHEMA `params.properties` — add:
```python
"cells": {"type": "array", "items": {"type": "array"}},
"features": {"type": "array", "items": {"type": "string"}},
"highlight": {"type": "object"},
```
3. Find the `ALLOWED` definition and add `"spreadsheet"` to it.
4. In `valid()`, before the final `return True`, add:
```python
if w == "spreadsheet":
    cells = p.get("cells")
    return isinstance(cells, list) and len(cells) > 0 and all(
        isinstance(row, list) and len(row) > 0 for row in cells)
```
5. In the `SYSTEM` widget menu (the bulleted list around lines 66–86) add:
```
- spreadsheet: an Excel/spreadsheet screen (a grid of cells) is shown → params
  {cells: 2D array of the visible values (headers + a few real rows), features:
  which of wrap/merge_center/orientation/bold/currency/percent this moment teaches,
  highlight: {row,col} of the focal cell}. Use the ACTUAL text/numbers in the frame.
```
And add `spreadsheet` to the enum line in the final "Reply with ONLY a JSON object" schema hint.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/test_valid_spreadsheet.py`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add analyze.py tests/test_valid_spreadsheet.py
git commit -m "feat: spreadsheet widget schema + valid() branch"
```

---

### Task 4: `spreadsheet` genre + non-mutating `system_for`

**Files:**
- Modify: `analyze.py` (GENRE_PROMPTS, GENRE_KEYWORDS, `system_for`, `apply_genre`, both backends' `ask`)
- Test: `tests/test_system_for.py`

**Interfaces:**
- Consumes: `SYSTEM`, `GENRE_PROMPTS`, `apply_genre` in `analyze.py`.
- Produces: `system_for(genre: str) -> str` (base SYSTEM when genre unknown/general); `MlxBackend.ask` / `OpenAIBackend.ask` accept optional `system: str | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_system_for.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import analyze

base = analyze.SYSTEM
s = analyze.system_for("spreadsheet")
assert "spreadsheet" in s.lower(), "spreadsheet genre block should mention spreadsheet"
assert "Reply with ONLY a JSON object" in s, "composed prompt keeps the JSON instruction"
assert analyze.system_for("general") == base, "general returns the base prompt unchanged"
assert analyze.SYSTEM == base, "system_for must NOT mutate the global SYSTEM"
print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/test_system_for.py`
Expected: FAIL — `AttributeError: module 'analyze' has no attribute 'system_for'`.

- [ ] **Step 3: Implement genre + system_for**

In `analyze.py`:
1. Add to `GENRE_PROMPTS`:
```python
"spreadsheet": (
    "This is a spreadsheet/Excel tutorial. Emit a `spreadsheet` widget: cells = the grid "
    "on screen (headers + a few real rows, exact values from the frame), features = the "
    "actions this moment teaches (wrap, merge_center, orientation, bold, currency, percent), "
    "highlight = {row,col} of the focal cell. The learner gets an editable grid to try it."
),
```
2. Add to `GENRE_KEYWORDS`:
```python
"spreadsheet": ["excel", "spreadsheet", "cell", "column", "row", "formula", "workbook", "sheet", "worksheet", "ribbon"],
```
3. Replace `apply_genre` with a non-mutating `system_for` + a thin `apply_genre` that delegates:
```python
def system_for(genre: str) -> str:
    """Compose base SYSTEM ⊕ genre lens WITHOUT mutating globals (safe for the live server)."""
    block = GENRE_PROMPTS.get(genre)
    if not block:
        return SYSTEM
    return SYSTEM.replace(
        "Reply with ONLY a JSON object:",
        f"GENRE LENS ({genre}): {block}\n\nReply with ONLY a JSON object:")


def apply_genre(genre: str) -> str:
    """Offline CLI path: set the module SYSTEM to the genre-composed prompt."""
    global SYSTEM
    SYSTEM = system_for(genre)
    return genre
```

- [ ] **Step 4: Thread `system=` through both backends**

In `MlxBackend.ask` signature: `def ask(self, frame, context, max_px=None, system=None):` and use `sys_prompt = system or SYSTEM` in the prompt string (`f'{sys_prompt}\n\n...'`).
In `OpenAIBackend.ask` signature: `def ask(self, frame, context, max_px=None, system=None):` and set the system message content to `system or SYSTEM`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python tests/test_system_for.py`
Expected: `OK`.

- [ ] **Step 6: Verify apply_genre still works for the offline CLI**

Run: `uv run python -c "import analyze; base=analyze.SYSTEM; analyze.apply_genre('spreadsheet'); assert analyze.SYSTEM!=base and 'spreadsheet' in analyze.SYSTEM.lower(); print('apply_genre OK')"`
Expected: `apply_genre OK`.

- [ ] **Step 7: Commit**

```bash
git add analyze.py tests/test_system_for.py
git commit -m "feat: spreadsheet genre + non-mutating system_for, ask(system=)"
```

---

### Task 5: Wire genre into the live serve.py path

**Files:**
- Modify: `agent/db.py` (add `video_genre`)
- Modify: `serve.py` (resolve genre, pass `system=`, bump PROMPT_VERSION)
- Test: `tests/test_video_genre.py`

**Interfaces:**
- Consumes: `analyze.system_for`, `analyze.detect_genre`, `db.video_genre`.
- Produces: `db.video_genre(video_id: str) -> str | None`; both serve endpoints call `backend.ask(..., system=analyze.system_for(genre))`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_video_genre.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from agent import db
db.load_env()
# unknown video → None (no row)
assert db.video_genre("__nope__" ) is None, "missing video → None"
print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/test_video_genre.py`
Expected: FAIL — `AttributeError: module 'agent.db' has no attribute 'video_genre'`.

- [ ] **Step 3: Add the db helper**

In `agent/db.py`, add:
```python
def video_genre(video_id):
    """The curator-assigned genre for a video, or None. Used by the live prompt path."""
    with conn() as c, c.cursor() as cur:
        cur.execute("select genre from videos where video_id=%s", (video_id,))
        row = cur.fetchone()
        return row[0] if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/test_video_genre.py`
Expected: `OK`.

- [ ] **Step 5: Wire genre resolution into serve.py**

In `serve.py`:
1. Add import: `import analyze` (or `from analyze import system_for, detect_genre` alongside the existing import).
2. Add a genre resolver with a tiny memo:
```python
_genre_cache: dict[str, str] = {}

def _genre_for(video: str) -> str:
    if video in _genre_cache:
        return _genre_cache[video]
    g = None
    if _db:
        try:
            g = _db.video_genre(video)
        except Exception:
            g = None
    g = g or "general"
    _genre_cache[video] = g
    return g
```
3. In `make_widget`, change the backend call to:
```python
raw = backend.ask(DATA / req.video / "frames" / fr["file"], context,
                  max_px=WIDGET_MAX_PX, system=analyze.system_for(_genre_for(req.video)))
```
4. In `make_region_widget`, change the backend call to:
```python
raw = backend.ask(path, context, system=analyze.system_for(_genre_for(req.video)))
```
5. Bump the cache version so the new prompt gets fresh keys:
```python
PROMPT_VERSION = "v2"
```

- [ ] **Step 6: Verify it builds/imports**

Run: `uv run python -c "import serve; print('serve imports OK')"`
Expected: `serve imports OK`.

- [ ] **Step 7: Commit**

```bash
git add agent/db.py serve.py tests/test_video_genre.py
git commit -m "feat: live genre-aware prompt in serve.py (video_genre + system_for)"
```

---

### Task 6: End-to-end on the Excel video

**Files:** none (verification only)

**Interfaces:**
- Consumes: everything above; the Excel video `5IgOP7Lpk5g` is symlinked into `data/`.

- [ ] **Step 1: Tag the Excel video's genre**

Run:
```bash
uv run python -c "from agent import db; db.load_env(); db.set_video_genre('5IgOP7Lpk5g','spreadsheet'); print(db.video_genre('5IgOP7Lpk5g'))"
```
Expected: `spreadsheet`.

- [ ] **Step 2: Scrub the video's cache so it's cold**

Run: `uv run python scripts/scrub_video.py 5IgOP7Lpk5g --yes`
(Note: this removes the DB rows including the genre set in Step 1 — re-run Step 1 after.) Then re-run Step 1.

- [ ] **Step 3: Start the stack**

Run: `./run.sh` and wait for `ready`. Confirm LM Studio serving qwen3-vl-4b via `curl -s http://127.0.0.1:8756/api/info`.

- [ ] **Step 4: Live-ask a spreadsheet moment**

Run (a moment where the grid is on screen, e.g. t=150):
```bash
curl -s -X POST http://127.0.0.1:8756/api/widget -H 'content-type: application/json' \
  -d '{"video":"5IgOP7Lpk5g","time":150,"text":"the column header month number takes up space so shrink it to fit","ask":"let me try this in a grid"}' | python3 -m json.tool
```
Expected: JSON with `"widget": "spreadsheet"` and a `params.cells` 2D array (not an `answer` card). If it still returns an answer, note it and inspect the raw VLM output — the genre prompt may need tightening (adjust `GENRE_PROMPTS["spreadsheet"]`, bump `PROMPT_VERSION`, re-test).

- [ ] **Step 5: Confirm in the UI + perf**

Open `http://localhost:5173/?v=5IgOP7Lpk5g`, scrub to the moment, select the passage, "make it interactive" → a spreadsheet widget renders and is editable. Open `?view=perf` → the event shows `widget_kind=spreadsheet` and `t_total_ms < 5000`.

- [ ] **Step 6: Regression check**

Live-ask a pre-baked STEM video (`kCc8FmEb1nY`, genre unset → base prompt) and confirm it still mints its usual widget kinds (matrix/attention/etc.), not spreadsheets.

- [ ] **Step 7: Commit any prompt tweaks made during Step 4**

```bash
git add analyze.py
git commit -m "chore: tune spreadsheet genre prompt from e2e"
```

---

## Self-Review

**Spec coverage:**
- Widget component + FEATURES registry → Task 2. Formula evaluator → Task 1. Merge → Task 2b. Params (cells/features/highlight) → Tasks 2, 3. Schema/ALLOWED/valid()/SYSTEM → Task 3. Genre + non-mutating system_for + ask(system=) → Task 4. Live serve.py wiring + video_genre → Task 5. End-to-end + regression → Task 6. All spec sections covered.

**Placeholder scan:** No TBD/TODO. Every code step shows complete code. The one deferred behavior (merge in Task 2) is explicitly completed in Task 2b, not left vague.

**Type consistency:** `evalFormula(src, grid, seen)` consistent across Tasks 1–2. `system_for(genre)->str` consistent Tasks 4–5. `video_genre(video_id)->str|None` consistent Task 5. `ask(..., max_px=None, system=None)` signature consistent Tasks 4–5 and matches the existing `max_px` param added earlier. `cells` shape (2D of values) consistent across widget, schema, genre prompt.

**Note on tests:** this repo has no test framework; the plan uses Node's built-in `node --test` (Node ≥22, already required) for the pure JS evaluator and plain `assert` scripts under `tests/` for Python. No new dependencies.
