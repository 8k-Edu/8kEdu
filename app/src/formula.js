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
  if (!rc || rc.r < 0 || rc.c < 0 || rc.r >= grid.length || rc.c >= grid[rc.r].length) throw new Error('REF')
  const key = rc.r + ',' + rc.c
  if (seen.has(key)) throw new Error('CYCLE')
  const raw = rawAt(grid, rc.r, rc.c)
  if (raw == null || raw === '') return 0
  if (typeof raw === 'string' && raw.startsWith('=')) {
    const s2 = new Set(seen); s2.add(key)
    const v = parseAll(tokenize(raw.slice(1)), grid, s2)
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
  const re = /\s*([A-Z]+[0-9]+|[A-Z]+|[0-9]*\.?[0-9]+|[()+\-*/,:])/y
  let pos = 0
  let m
  while ((m = re.exec(src))) {
    toks.push(m[1])
    pos = re.lastIndex
  }
  // Anything left besides trailing whitespace means the source had
  // characters the tokenizer couldn't recognize (e.g. `5%2`) — malformed.
  if (/\S/.test(src.slice(pos))) throw new Error('REF')
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
  if (t === '(') {
    pos.i++
    const v = evalExpr(toks, pos, grid, seen)
    if (toks[pos.i] !== ')') throw new Error('REF')
    pos.i++
    return v
  }
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

// Parses every token in `toks` as a single expression. Throws if any tokens
// are left over (e.g. a stray trailing `)`), so malformed formulas surface
// as #REF! instead of silently returning whatever partial value parsed.
function parseAll(toks, grid, seen) {
  const pos = { i: 0 }
  const v = evalExpr(toks, pos, grid, seen)
  if (pos.i !== toks.length) throw new Error('REF')
  return v
}

export function evalFormula(src, grid, seen = new Set()) {
  if (typeof src !== 'string' || !src.startsWith('=')) {
    const n = Number(src)
    return src !== '' && !Number.isNaN(n) ? n : src
  }
  try {
    const v = parseAll(tokenize(src.slice(1)), grid, seen)
    return typeof v === 'number' && Number.isFinite(v) ? v : '#REF!'
  } catch (e) {
    return e.message === 'CYCLE' ? '#CYCLE' : '#REF!'
  }
}
