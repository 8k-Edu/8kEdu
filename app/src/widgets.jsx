import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// ---------- Alammar-style role colors (Illustrated Transformer) ----------
export const ROLE = {
  q: '#b48eff',   // queries — purple
  k: '#ffab70',   // keys — orange
  v: '#79c0ff',   // values — blue
  w: '#56d364',   // weights / outputs — green
}

const card = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 12,
  padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
}

function heat(v, lo, hi, hue = 210) {
  const t = hi === lo ? 0.5 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)))
  return `hsl(${hue}, 65%, ${18 + t * 38}%)`
}

export const resizeMatrix = (m, rows, cols) =>
  Array.from({ length: rows }, (_, i) =>
    Array.from({ length: cols }, (_, j) => m[i]?.[j] ?? 0))

const MDIM_MIN = 1, MDIM_MAX = 6

function DimStepper({ label, value, onChange, color }) {
  const btn = {
    background: 'none', border: '1px solid #30363d', color: '#8b949e',
    borderRadius: 4, width: 16, height: 16, fontSize: 10, lineHeight: '13px', padding: 0,
  }
  return (
    <span style={{ display: 'inline-flex', gap: 2, alignItems: 'center', marginLeft: 6 }}>
      <button style={btn} disabled={value <= MDIM_MIN} onClick={() => onChange(value - 1)}>−</button>
      <span style={{ fontSize: 10, color, minWidth: 26, textAlign: 'center' }}>{value} {label}</span>
      <button style={btn} disabled={value >= MDIM_MAX} onClick={() => onChange(value + 1)}>+</button>
    </span>
  )
}

// fill generators — the matrix toolkit
const FILLS = [
  { key: 'dice', icon: '🎲', hint: 'random ints 0–9', gen: (r, c) => grid(r, c, () => Math.floor(Math.random() * 10)) },
  { key: 'noise', icon: '±', hint: 'random −1…1', gen: (r, c) => grid(r, c, () => Math.round((Math.random() * 2 - 1) * 10) / 10) },
  { key: 'eye', icon: 'I', hint: 'identity', gen: (r, c) => grid(r, c, (i, j) => (i === j ? 1 : 0)) },
  { key: 'tril', icon: '◣', hint: 'lower-triangular ones', gen: (r, c) => grid(r, c, (i, j) => (j <= i ? 1 : 0)) },
  { key: 'zeros', icon: '0', hint: 'zeros', gen: (r, c) => grid(r, c, () => 0) },
]
const grid = (r, c, f) => Array.from({ length: r }, (_, i) => Array.from({ length: c }, (_, j) => f(i, j)))

function MatrixToolkit({ m, onChange, color }) {
  return (
    <span style={{ display: 'inline-flex', gap: 3, marginLeft: 8 }}>
      {FILLS.map(f => (
        <button key={f.key} title={f.hint}
          onClick={() => onChange(f.gen(m.length, m[0].length))}
          style={{
            background: 'none', border: '1px solid #30363d', color: color ?? '#8b949e',
            borderRadius: 4, minWidth: 18, height: 17, fontSize: 10, lineHeight: '14px', padding: '0 3px',
          }}>{f.icon}</button>
      ))}
    </span>
  )
}

function MatrixInput({ m, onChange, label, color = '#8b949e', resizable = true, lockRows = false, lockCols = false }) {
  const [rows, cols] = [m.length, m[0].length]
  return (
    <div>
      <div style={{ fontSize: 12, color, marginBottom: 4, fontWeight: 600, display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
        {label}
        {resizable && !lockRows && <DimStepper label="r" value={rows} color={color} onChange={r => onChange(resizeMatrix(m, r, cols))} />}
        {resizable && !lockCols && <DimStepper label="c" value={cols} color={color} onChange={c => onChange(resizeMatrix(m, rows, c))} />}
        <MatrixToolkit m={m} onChange={onChange} color={color} />
      </div>
      <div style={{ display: 'grid', gap: 4, gridTemplateColumns: `repeat(${m[0].length}, auto)`, width: 'fit-content' }}>
        {m.map((row, i) => row.map((v, j) => (
          <input key={`${i}-${j}`} type="number" step="0.5" value={v}
            style={{ borderColor: color + '55' }}
            onChange={e => {
              const next = m.map(r => [...r])
              next[i][j] = parseFloat(e.target.value) || 0
              onChange(next)
            }} />
        )))}
      </div>
    </div>
  )
}

function MatrixView({ m, label, colorize, hue = 210, color = '#8b949e' }) {
  const flat = m.flat()
  const [lo, hi] = [Math.min(...flat), Math.max(...flat)]
  return (
    <div>
      <div style={{ fontSize: 12, color, marginBottom: 4, fontWeight: 600 }}>{label}</div>
      <div style={{ display: 'grid', gap: 4, gridTemplateColumns: `repeat(${m[0].length}, auto)`, width: 'fit-content' }}>
        {m.map((row, i) => row.map((v, j) => (
          <div key={`${i}-${j}`} style={{
            width: 52, padding: '5px 0', textAlign: 'center', borderRadius: 6, fontSize: 13,
            background: colorize ? heat(v, lo, hi, hue) : '#0d1117', border: '1px solid #30363d',
          }}>{Number.isInteger(v) ? v : v.toFixed(2)}</div>
        )))}
      </div>
    </div>
  )
}

const matmul = (a, b) =>
  a.map(row => b[0].map((_, j) => row.reduce((s, v, k) => s + v * b[k][j], 0)))

const softmaxRow = (row, temp = 1) => {
  const mx = Math.max(...row)
  const ex = row.map(v => Math.exp((v - mx) / temp))
  const sum = ex.reduce((s, v) => s + v, 0)
  return ex.map(v => v / sum)
}

function TempSlider({ temp, setTemp, min = 0.05 }) {
  return (
    <label style={{ fontSize: 12, color: '#8b949e' }}>
      temperature {temp.toFixed(2)} — low = sharp, high = uniform
      <input type="range" min={min} max="5" step="0.05" value={temp} style={{ width: '100%' }}
        onChange={e => setTemp(parseFloat(e.target.value))} />
    </label>
  )
}

// ---------- the four widgets (all report live state via onState) ----------

export function MatrixMul({ params, onState }) {
  const [a, setA] = useState(params.a ?? [[1, 2], [3, 4]])
  const [b, setB] = useState(params.b ?? [[5, 6], [7, 8]])
  useEffect(() => { onState?.({ a, b }) }, [a, b, onState])
  const changeA = (next) => {
    setA(next)
    if (next[0].length !== b.length) setB(resizeMatrix(b, next[0].length, b[0].length))
  }
  const changeB = (next) => {
    setB(next.length === a[0].length ? next : resizeMatrix(next, a[0].length, next[0].length))
  }
  const ok = a[0].length === b.length
  const c = useMemo(() => (ok ? matmul(a, b) : null), [a, b, ok])
  return (
    <div style={card}>
      <div style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <MatrixInput m={a} onChange={changeA} label={`A (${a.length}×${a[0].length})`} color={ROLE.q} />
        <span style={{ fontSize: 22, color: '#8b949e' }}>×</span>
        <MatrixInput m={b} onChange={changeB} label={`B (${b.length}×${b[0].length}) — rows follow A`} color={ROLE.k} lockRows />
        <span style={{ fontSize: 22, color: '#8b949e' }}>=</span>
        {ok ? <MatrixView m={c} label="A·B — edit inputs, watch it move" colorize hue={130} color={ROLE.w} />
            : <span style={{ color: '#f85149' }}>shape mismatch</span>}
      </div>
    </div>
  )
}

export function Attention({ params, onState }) {
  const [q, setQ] = useState(params.q ?? [[1, 0], [0, 1], [1, 1]])
  const [k, setK] = useState(params.k ?? [[1, 0], [0, 1], [1, -1]])
  const [temp, setTemp] = useState(params.temperature ?? 1)
  useEffect(() => { onState?.({ q, k, temperature: temp }) }, [q, k, temp, onState])
  const changeQ = (next) => {
    setQ(next)
    if (next[0].length !== k[0].length) setK(resizeMatrix(k, k.length, next[0].length))
  }
  const changeK = (next) => {
    setK(next)
    if (next[0].length !== q[0].length) setQ(resizeMatrix(q, q.length, next[0].length))
  }
  const weights = useMemo(() => {
    const kt = k[0].map((_, j) => k.map(r => r[j]))
    const scale = Math.sqrt(q[0].length)
    return matmul(q, kt).map(r => softmaxRow(r.map(v => v / scale), temp))
  }, [q, k, temp])
  return (
    <div style={card}>
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        <MatrixInput m={q} onChange={changeQ} label="Q — queries" color={ROLE.q} />
        <MatrixInput m={k} onChange={changeK} label="K — keys (d follows Q)" color={ROLE.k} />
        <MatrixView m={weights} label="softmax(QKᵀ/√d) — attention" colorize hue={130} color={ROLE.w} />
      </div>
      <TempSlider temp={temp} setTemp={setTemp} min={0.1} />
    </div>
  )
}

export function Softmax({ params, onState }) {
  const [logits, setLogits] = useState(params.logits ?? [2, 1, 0.5, -1])
  const [temp, setTemp] = useState(params.temperature ?? 1)
  useEffect(() => { onState?.({ logits, temperature: temp }) }, [logits, temp, onState])
  const probs = softmaxRow(logits, temp)
  return (
    <div style={card}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {logits.map((v, i) => (
          <input key={i} type="number" step="0.5" value={v}
            style={{ borderColor: ROLE.v + '55' }}
            onChange={e => {
              const next = [...logits]; next[i] = parseFloat(e.target.value) || 0; setLogits(next)
            }} />
        ))}
        <button onClick={() => logits.length > 2 && setLogits(logits.slice(0, -1))} style={{
          background: 'none', border: '1px solid #30363d', color: '#8b949e', borderRadius: 6, width: 22, height: 22, fontSize: 12,
        }}>−</button>
        <button onClick={() => logits.length < 8 && setLogits([...logits, 0])} style={{
          background: 'none', border: '1px solid #30363d', color: '#8b949e', borderRadius: 6, width: 22, height: 22, fontSize: 12,
        }}>+</button>
        <button title="random logits" onClick={() => setLogits(logits.map(() => Math.round((Math.random() * 5 - 2) * 10) / 10))} style={{
          background: 'none', border: '1px solid #30363d', color: '#8b949e', borderRadius: 6, width: 22, height: 22, fontSize: 11,
        }}>🎲</button>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 120 }}>
        {probs.map((p, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: '#8b949e' }}>
            <div style={{ height: p * 100 + 2, background: heat(p, 0, 1, 130), borderRadius: '6px 6px 0 0', transition: 'height .15s' }} />
            {(p * 100).toFixed(0)}%
          </div>
        ))}
      </div>
      <TempSlider temp={temp} setTemp={setTemp} />
    </div>
  )
}

export function FunctionPlot({ params, onState }) {
  const sliders = params.sliders ?? []
  const [vals, setVals] = useState(Object.fromEntries(sliders.map(s => [s.name, s.value])))
  const expr = params.expr ?? 'Math.sin(x)'
  useEffect(() => {
    onState?.({ expr, sliders: sliders.map(s => ({ ...s, value: vals[s.name] ?? s.value })) })
  }, [vals, expr, onState]) // eslint-disable-line react-hooks/exhaustive-deps
  const fn = useMemo(() => {
    try {
      // demo-scoped: expr comes from our own curated pipeline, args are numbers
      return new Function('x', ...Object.keys(vals), `"use strict"; return (${expr});`)
    } catch { return null }
  }, [expr, vals])
  const pts = useMemo(() => {
    if (!fn) return ''
    const args = Object.values(vals)
    const ys = []
    for (let i = 0; i <= 200; i++) {
      const x = -6 + (12 * i) / 200
      let y; try { y = fn(x, ...args) } catch { y = 0 }
      ys.push([x, Number.isFinite(y) ? y : 0])
    }
    const ymax = Math.max(4, ...ys.map(p => Math.abs(p[1])))
    return ys.map(([x, y]) => `${((x + 6) / 12) * 400},${100 - (y / ymax) * 90}`).join(' ')
  }, [fn, vals])
  return (
    <div style={card}>
      <code style={{ fontSize: 13, color: ROLE.v }}>y = {expr}</code>
      <svg viewBox="0 0 400 200" style={{ background: '#0d1117', borderRadius: 8 }}>
        <line x1="0" y1="100" x2="400" y2="100" stroke="#30363d" />
        <line x1="200" y1="0" x2="200" y2="200" stroke="#30363d" />
        <polyline points={pts} fill="none" stroke={ROLE.v} strokeWidth="2" />
      </svg>
      {sliders.map(s => (
        <label key={s.name} style={{ fontSize: 12, color: '#8b949e' }}>
          {s.name} = {(vals[s.name] ?? s.value).toFixed(2)}
          <input type="range" min={s.min} max={s.max} step={(s.max - s.min) / 100}
            value={vals[s.name] ?? s.value} style={{ width: '100%' }}
            onChange={e => setVals({ ...vals, [s.name]: parseFloat(e.target.value) })} />
        </label>
      ))}
    </div>
  )
}

// ---------- tier 2: composable grammar — components + exprs, no codegen ----------
// spec: { widget: "composite", components: [{id, type, ...}], }
// expr components recompute from a scope of all earlier component values.

const ENV = {
  matmul,
  softmax: (v, t = 1) => softmaxRow(v, t),
  rowNormalize: (m) => m.map(r => {
    const s = r.reduce((a, b) => a + b, 0) || 1
    return r.map(v => v / s)
  }),
  lowerTriOnes: (n) => Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (j <= i ? 1 : 0))),
  transpose: (m) => m[0].map((_, j) => m.map(r => r[j])),
  range: (n) => Array.from({ length: Math.max(0, Math.floor(n)) }, (_, i) => i),
  round: (x, d = 2) => Math.round(x * 10 ** d) / 10 ** d,
  Math,
}

function evalExpr(expr, scope) {
  try {
    // curated source: exprs come from our pipeline specs, scope values are data
    const names = [...Object.keys(ENV), ...Object.keys(scope)]
    const vals = [...Object.values(ENV), ...Object.values(scope)]
    return new Function(...names, `"use strict"; return (${expr});`)(...vals)
  } catch {
    return null
  }
}

function CompositeStage({ comp, value, scope, onInput }) {
  const t = comp.type
  if (t === 'slider') {
    return (
      <label style={{ fontSize: 12, color: '#8b949e' }}>
        {comp.label ?? comp.id} = {typeof value === 'number' ? value.toFixed(comp.step >= 1 ? 0 : 2) : value}
        <input type="range" min={comp.min ?? 0} max={comp.max ?? 10} step={comp.step ?? (((comp.max ?? 10) - (comp.min ?? 0)) / 100 || 0.1)}
          value={value} style={{ width: '100%' }}
          onChange={e => onInput(parseFloat(e.target.value))} />
      </label>
    )
  }
  if (t === 'matrix') {
    const m = value
    if (!Array.isArray(m) || !Array.isArray(m[0])) return null
    return comp.editable
      ? <MatrixInput m={m} onChange={onInput} label={comp.label ?? comp.id} color={comp.color ?? ROLE.q} />
      : <MatrixView m={m} label={comp.label ?? comp.id} colorize={false} color={comp.color ?? '#8b949e'} />
  }
  if (t === 'heatmap') {
    const m = value
    if (!Array.isArray(m) || !Array.isArray(m[0])) return null
    return <MatrixView m={m} label={comp.label ?? comp.id} colorize hue={comp.hue ?? 130} color={comp.color ?? ROLE.w} />
  }
  if (t === 'bars') {
    const v = Array.isArray(value) ? value : []
    const mx = Math.max(1e-9, ...v.map(Math.abs))
    return (
      <div>
        <div style={{ fontSize: 12, color: comp.color ?? ROLE.v, fontWeight: 600, marginBottom: 4 }}>{comp.label ?? comp.id}</div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', height: 90 }}>
          {v.map((x, i) => (
            <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, color: '#8b949e' }}>
              <div style={{ height: (Math.abs(x) / mx) * 78 + 2, background: heat(x, -mx, mx, comp.hue ?? 210), borderRadius: '4px 4px 0 0', transition: 'height .12s' }} />
              {ENV.round(x)}
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (t === 'plot') {
    const pts = []
    for (let i = 0; i <= 160; i++) {
      const x = (comp.xmin ?? -6) + ((comp.xmax ?? 6) - (comp.xmin ?? -6)) * i / 160
      const y = evalExpr(comp.expr, { ...scope, x })
      pts.push([x, Number.isFinite(y) ? y : 0])
    }
    const ymax = Math.max(1e-9, ...pts.map(p => Math.abs(p[1])))
    const poly = pts.map(([x, y]) =>
      `${((x - (comp.xmin ?? -6)) / ((comp.xmax ?? 6) - (comp.xmin ?? -6))) * 400},${100 - (y / ymax) * 88}`).join(' ')
    return (
      <div>
        <div style={{ fontSize: 12, color: comp.color ?? ROLE.v, fontWeight: 600, marginBottom: 4 }}>{comp.label ?? comp.expr}</div>
        <svg viewBox="0 0 400 200" style={{ background: '#0d1117', borderRadius: 8, width: '100%' }}>
          <line x1="0" y1="100" x2="400" y2="100" stroke="#30363d" />
          <polyline points={poly} fill="none" stroke={comp.color ?? ROLE.v} strokeWidth="2" />
        </svg>
      </div>
    )
  }
  if (t === 'text') {
    return <div style={{ fontSize: 13, color: '#c9d1d9' }}>{comp.value}</div>
  }
  if (t === 'value') {
    return (
      <div style={{ fontSize: 13, color: '#8b949e' }}>
        {comp.label ?? comp.id}: <b style={{ color: '#e6edf3', fontVariantNumeric: 'tabular-nums' }}>
          {typeof value === 'number' ? ENV.round(value, 4) : JSON.stringify(value)}</b>
      </div>
    )
  }
  return null
}

export function Composite({ params, onState }) {
  const comps = params.components ?? []
  const [inputs, setInputs] = useState(() => {
    if (params.inputs) return params.inputs // remixed state from a share link
    const init = {}
    comps.forEach(c => {
      if (c.type === 'slider') init[c.id] = c.value ?? c.min ?? 0
      else if (c.type === 'matrix' && c.editable) init[c.id] = c.value ?? [[1, 0], [0, 1]]
    })
    return init
  })
  useEffect(() => { onState?.({ ...params, inputs }) }, [inputs]) // eslint-disable-line react-hooks/exhaustive-deps

  // linear dataflow: each component sees all earlier values in scope
  const scope = {}
  const rendered = comps.map(c => {
    let value
    if (c.id in inputs) value = inputs[c.id]
    else if (c.expr) value = evalExpr(c.expr, scope)
    else value = c.value
    scope[c.id] = value
    return (
      <CompositeStage key={c.id} comp={c} value={value} scope={scope}
        onInput={v => setInputs(s => ({ ...s, [c.id]: v }))} />
    )
  })
  return <div style={{ ...card }}>{rendered}</div>
}

// ---------- tier 3: pyodide notebook — real numpy/scipy/sympy/matplotlib ----------

// Primary: jsDelivr CDN (matches installed pyodide npm version). Fallback: local
// vendor under data/pyodide-dist/ (served by Vite's publicDir) — keeps the demo alive
// if the CDN is unreachable. Populate the local dir with scripts/vendor-pyodide.sh.
const PYODIDE_CDN = 'https://cdn.jsdelivr.net/pyodide/v314.0.2/full/'
const PYODIDE_LOCAL = '/pyodide-dist/'

async function pickIndexURL() {
  try {
    const r = await fetch(PYODIDE_CDN + 'pyodide-lock.json', { method: 'HEAD', cache: 'no-store' })
    if (r.ok) return PYODIDE_CDN
  } catch { /* offline or blocked — fall through to local vendor */ }
  return PYODIDE_LOCAL
}

let pyodidePromise = null
function getPyodide() {
  if (!pyodidePromise) {
    pyodidePromise = (async () => {
      const { loadPyodide } = await import('pyodide')
      const indexURL = await pickIndexURL()
      const py = await loadPyodide({ indexURL })
      await py.loadPackage(['numpy', 'matplotlib'])
      await py.runPythonAsync(`
import sys, io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def _capture(code, env):
    out = io.StringIO()
    old = sys.stdout
    sys.stdout = out
    try:
        exec(code, env)
    finally:
        sys.stdout = old
    imgs = []
    for n in plt.get_fignums():
        buf = io.BytesIO()
        plt.figure(n).savefig(buf, format="png", dpi=80, bbox_inches="tight",
                              facecolor="#161b22", edgecolor="none")
        imgs.append(base64.b64encode(buf.getvalue()).decode())
    plt.close("all")
    return out.getvalue(), imgs
`)
      return py
    })()
  }
  return pyodidePromise
}

export function Notebook({ params, onState }) {
  const [cells, setCells] = useState(params.cells ?? ['import numpy as np\nprint(np.eye(3))'])
  const [vals, setVals] = useState(
    Object.fromEntries((params.sliders ?? []).map(s => [s.name, s.value]))
  )
  const [outputs, setOutputs] = useState([])
  const [status, setStatus] = useState('loading python… (~10s first time)')
  const runId = useRef(0)
  useEffect(() => { onState?.({ ...params, cells, sliders: (params.sliders ?? []).map(s => ({ ...s, value: vals[s.name] ?? s.value })) }) },
    [cells, vals]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(async (curCells, curVals) => {
    const id = ++runId.current
    try {
      const py = await getPyodide()
      if (id !== runId.current) return
      setStatus('running…')
      const env = py.toPy({ ...curVals })
      await py.runPythonAsync('import builtins')
      const results = []
      for (const cell of curCells) {
        try {
          const capture = py.globals.get('_capture')
          const res = capture(cell, env)
          const [text, imgs] = [res.get(0), res.get(1).toJs()]
          results.push({ text, imgs })
          res.destroy?.()
        } catch (e) {
          results.push({ text: String(e).split('\n').slice(-3).join('\n'), error: true, imgs: [] })
          break
        }
      }
      if (id === runId.current) { setOutputs(results); setStatus(null) }
    } catch (e) {
      if (id === runId.current) setStatus(`python failed to load: ${String(e).slice(0, 80)}`)
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => run(cells, vals), 350) // debounce slider drags
    return () => clearTimeout(t)
  }, [cells, vals, run])

  return (
    <div style={{ ...card }}>
      {(params.sliders ?? []).map(s => (
        <label key={s.name} style={{ fontSize: 12, color: '#8b949e' }}>
          {s.name} = {(vals[s.name] ?? s.value)}
          <input type="range" min={s.min} max={s.max} step={s.step ?? 1}
            value={vals[s.name] ?? s.value} style={{ width: '100%' }}
            onChange={e => setVals({ ...vals, [s.name]: parseFloat(e.target.value) })} />
        </label>
      ))}
      {cells.map((c, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <textarea value={c} spellCheck={false}
            onChange={e => setCells(cs => cs.map((x, j) => (j === i ? e.target.value : x)))}
            rows={Math.min(10, c.split('\n').length + 1)}
            style={{
              width: '100%', background: '#0d1117', color: '#c9d1d9', border: '1px solid #30363d',
              borderRadius: 8, padding: 10, fontSize: 12.5, fontFamily: 'ui-monospace, monospace',
              lineHeight: 1.5, resize: 'vertical',
            }} />
          {outputs[i] && (
            <div style={{ fontSize: 12, fontFamily: 'ui-monospace, monospace', whiteSpace: 'pre-wrap',
                          color: outputs[i].error ? '#f85149' : '#7ee787', padding: '0 4px' }}>
              {outputs[i].text}
              {outputs[i].imgs?.map((b64, k) => (
                <img key={k} src={`data:image/png;base64,${b64}`} alt="plot"
                  style={{ display: 'block', maxWidth: '100%', borderRadius: 8, marginTop: 6 }} />
              ))}
            </div>
          )}
        </div>
      ))}
      <div style={{ fontSize: 11, color: '#8b949e' }}>
        {status ?? 'live python (numpy · matplotlib · scipy · sympy on demand) — edit anything, it re-runs'}
      </div>
    </div>
  )
}

export const WIDGETS = {
  matrix_mul: MatrixMul,
  attention: Attention,
  softmax: Softmax,
  function_plot: FunctionPlot,
  composite: Composite,
  notebook: Notebook,
}
