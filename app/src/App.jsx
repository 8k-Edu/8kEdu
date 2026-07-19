import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import QRCode from 'qrcode'
import { WIDGETS } from './widgets.jsx'
import { buildDeckHtml, buildMarkdown, buildNotebook, download } from './exporters.js'

const TYPE_ICON = {
  matrix_mul: '✕', attention: '◧', softmax: '▮', function_plot: '∿', composite: '⧉', notebook: '🐍',
}

const TYPE_COLOR = {
  matrix_mul: '#b48eff', attention: '#ffab70', softmax: '#79c0ff',
  function_plot: '#56d364', composite: '#f2cc60', notebook: '#ff9bce',
}

const ROLES = {
  student: { icon: '🎓', label: 'student', tab: 'transcript', primary: '📓 notebook' },
  teacher: { icon: '👩‍🏫', label: 'teacher', tab: 'moments', primary: '🖥 deck / pdf' },
  creator: { icon: '✍️', label: 'creator', tab: 'moments', primary: '📝 markdown' },
  researcher: { icon: '🔬', label: 'researcher', tab: 'transcript', primary: '📓 notebook' },
}

const DEFAULT_URL = 'https://www.youtube.com/watch?v=kCc8FmEb1nY' // Karpathy — Let's build GPT

// the showcase shelf — videos with pipeline data available, grouped by theme.
// `inside` = the real artifacts the agent produced from each (sneak peek).
const CATEGORIES = [
  {
    name: 'AI & STEM', icon: '🧠',
    videos: [
      { id: 'kCc8FmEb1nY', title: "Karpathy — Let's build GPT from scratch",
        inside: { count: '55 touchable moments', mix: [['#79c0ff', 17], ['#ffab70', 16], ['#b48eff', 11], ['#56d364', 10], ['#ff9bce', 1]],
          peek: [['57:11', 'Masked self-attention, live', '#ffab70'], ['106:38', 'GELU curve you can drag', '#56d364'], ['63:20', 'The tril trick — runnable numpy', '#ff9bce']] } },
      { id: '42L1q1Z4Ojc', title: 'VisualAI — Multi-Head Attention Explained Visually',
        inside: { count: '4 attention widgets · by Nemotron Omni', mix: [['#ffab70', 4]],
          peek: [['3:10', 'Self-attention weights, editable', '#ffab70'], ['4:40', 'Multi-head split — 512 dims', '#ffab70'], ['5:30', 'Q·Kᵀ heatmap you can drag', '#ffab70']] } },
    ],
  },
  {
    name: 'How-To', icon: '🍳',
    videos: [
      { id: '9-ODDKHRVkA', title: 'The Best Scrambled Eggs You\'ll Ever Make (Restaurant Technique)',
        inside: { count: '2 live cook-controllers · by Nemotron Omni', mix: [['#b48eff', 1], ['#56d364', 1]],
          peek: [['0:50', 'Timing calculator — runnable', '#b48eff'], ['2:40', 'Doneness curve you can drag', '#56d364'], ['lens', 'how_to genre lens', '#ffab70']] } },
    ],
  },
  {
    name: 'Real estate', icon: '🏠',
    videos: [
      { id: 'BV6i8MNZ-BI', title: 'How to Buy your First House [Noob vs Pro] — $0 to Millionaire',
        inside: { count: '6 live calculators', mix: [['#ff9bce', 6]],
          peek: [['5:30', 'Mortgage & PMI calculator', '#ff9bce'], ['2:20', 'Cost of waiting: Noob vs Pro', '#ff9bce'], ['9:10', 'Sell vs hold — your numbers', '#ff9bce']] } },
    ],
  },
  {
    name: 'Fintech & markets', icon: '💰',
    videos: [
      { id: '3FZipnSI_po', title: 'Andrei Jikh — Japan Just Broke the Global Economy',
        inside: { count: '8 live simulators', mix: [['#ff9bce', 8]],
          peek: [['6:50', 'Yen carry trade simulator', '#ff9bce'], ['18:40', 'DCA vs currency devaluation', '#ff9bce'], ['17:00', 'Debt sustainability curve', '#ff9bce']] } },
    ],
  },
]
const VIDEOS = CATEGORIES.flatMap(c => c.videos.map(v => ({ ...v, tag: c.name })))
const INGESTED = VIDEOS.map(v => v.id)

// map the agent's genres to gallery shelves (+ icons for shelves the curator invents)
const GENRE_TO_CAT = { ai_stem: 'AI & STEM', how_to: 'How-To', real_estate: 'Real estate', finance: 'Fintech & markets', cooking: 'Cooking', fitness: 'Fitness', unknown: 'More' }
const CAT_ICON = { 'AI & STEM': '🧠', 'How-To': '🍳', 'Real estate': '🏠', 'Fintech & markets': '💰', 'Cooking': '🍜', 'Fitness': '🏋️', 'More': '✨' }
const WKIND_COLOR = { softmax: '#ff9bce', attention: '#ffab70', matrix_mul: '#79c0ff', function_plot: '#56d364', notebook: '#b48eff', composite: '#79c0ff' }

// merge curator-discovered videos (from Supabase) into the hardcoded featured shelves
function mergeGallery(live) {
  const cats = CATEGORIES.map(c => ({ ...c, videos: [...c.videos] }))
  const byName = Object.fromEntries(cats.map(c => [c.name, c]))
  const seen = new Set(VIDEOS.map(v => v.id))
  for (const v of (live || [])) {
    if (seen.has(v.video_id)) continue
    seen.add(v.video_id)
    const name = GENRE_TO_CAT[v.genre] || 'More'
    let cat = byName[name]
    if (!cat) { cat = { name, icon: CAT_ICON[name] || '✨', videos: [] }; byName[name] = cat; cats.push(cat) }
    const kinds = (v.widget_kinds || []).filter(Boolean)
    const mix = kinds.length ? kinds.map(k => [WKIND_COLOR[k] || '#8ee23e', 1]) : [['#8ee23e', 1]]
    cat.videos.push({
      id: v.video_id, title: v.title, agent: true,
      inside: {
        count: `${v.widgets} widget${v.widgets === 1 ? '' : 's'} · added by the curator`,
        mix,
        peek: [['new', 'freshly framed by Nemotron', '#8ee23e'], ['live', `${v.widgets} interactive widgets`, '#79c0ff']],
      },
    })
  }
  return cats
}

const parseVideoId = (url) => {
  const m = url.match(/(?:v=|youtu\.be\/|embed\/)([\w-]{11})/) || url.match(/^([\w-]{11})$/)
  return m ? m[1] : null
}

const b64enc = (obj) => btoa(unescape(encodeURIComponent(JSON.stringify(obj))))
const b64dec = (s) => JSON.parse(decodeURIComponent(escape(atob(s))))

function specFromHash() {
  const m = location.hash.match(/#s=(.+)/)
  if (!m) return null
  try { return b64dec(m[1]) } catch { return null }
}

function useYouTube(videoId) {
  const holder = useRef(null)
  const player = useRef(null)
  const [time, setTime] = useState(0)
  useEffect(() => {
    const boot = () => {
      player.current = new window.YT.Player(holder.current, {
        videoId,
        playerVars: { modestbranding: 1, rel: 0 },
      })
    }
    if (window.YT?.Player) boot()
    else {
      const s = document.createElement('script')
      s.src = 'https://www.youtube.com/iframe_api'
      document.head.appendChild(s)
      window.onYouTubeIframeAPIReady = boot
    }
    const poll = setInterval(() => {
      const t = player.current?.getCurrentTime?.()
      if (typeof t === 'number') setTime(t)
    }, 500)
    return () => clearInterval(poll)
  }, [videoId])
  const seek = (t) => player.current?.seekTo?.(t, true)
  return { holder, time, seek }
}

function ShareModal({ url, onClose }) {
  const [qr, setQr] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    QRCode.toDataURL(url, { width: 380, margin: 1, color: { dark: '#0d1117', light: '#e6edf3' } })
      .then(setQr)
  }, [url])
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 10,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: '#161b22', border: '1px solid #30363d', borderRadius: 16, padding: 24,
        display: 'flex', flexDirection: 'column', gap: 14, alignItems: 'center', maxWidth: 460,
      }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>remix this — exact state, your phone</div>
        {qr && <img src={qr} alt="QR" style={{ borderRadius: 12, width: 320, maxWidth: '80vw' }} />}
        <button onClick={() => { navigator.clipboard.writeText(url); setCopied(true) }} style={{
          background: copied ? '#238636' : '#2f81f7', color: 'white', border: 'none',
          borderRadius: 8, padding: '10px 18px', fontSize: 14, fontWeight: 600,
        }}>{copied ? 'copied ✓' : 'copy link'}</button>
        <div style={{ fontSize: 11, color: '#8b949e', wordBreak: 'break-all', maxWidth: 400 }}>{url.slice(0, 90)}…</div>
      </div>
    </div>
  )
}

// ---------- transcript: reading surface AND creation surface ----------

export const fmt = (t) => {
  t = Math.max(0, Math.floor(t))
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
           : `${m}:${String(s).padStart(2, '0')}`
}

const chip = {
  background: '#1f6feb26', color: '#4493f8', border: 'none', borderRadius: 6,
  fontSize: 11.5, fontWeight: 600, padding: '2px 7px', cursor: 'pointer',
  fontVariantNumeric: 'tabular-nums', flexShrink: 0,
}

function Chapters({ chapters, time, seek }) {
  const row = useRef(null)
  const activeIdx = chapters.findLastIndex(c => c.start <= time)
  useEffect(() => {
    row.current?.querySelector(`[data-ch="${activeIdx}"]`)
      ?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [activeIdx])
  return (
    <div ref={row} style={{
      display: 'flex', gap: 8, overflowX: 'auto', padding: '2px 0 8px', scrollbarWidth: 'thin',
    }}>
      {chapters.map((c, i) => (
        <button key={i} data-ch={i} onClick={() => seek(c.start)} style={{
          display: 'flex', gap: 7, alignItems: 'center', whiteSpace: 'nowrap',
          background: i === activeIdx ? '#1f6feb33' : '#161b22',
          border: `1px solid ${i === activeIdx ? '#388bfd66' : '#30363d'}`,
          color: i === activeIdx ? '#e6edf3' : '#8b949e',
          borderRadius: 8, padding: '5px 10px', fontSize: 12,
        }}>
          <span style={{ ...chip, padding: '1px 6px' }}>{fmt(c.start)}</span>
          {c.title.length > 42 ? c.title.slice(0, 40) + '…' : c.title}
        </button>
      ))}
    </div>
  )
}

function Moments({ concepts, chapters, active, onPick, checked, setChecked }) {
  const groups = useMemo(() => {
    const bounds = chapters.map(c => c.start)
    const out = []
    concepts.forEach(c => {
      let gi = bounds.findLastIndex(b => b <= c.time)
      gi = Math.max(0, gi)
      if (!out.length || out[out.length - 1].gi !== gi) {
        out.push({ gi, title: chapters[gi]?.title ?? 'intro', items: [] })
      }
      out[out.length - 1].items.push(c)
    })
    return out
  }, [concepts, chapters])
  const toggle = (t) => setChecked(s => {
    const next = new Set(s); next.has(t) ? next.delete(t) : next.add(t); return next
  })
  return (
    <div style={{ maxHeight: 340, overflowY: 'auto', background: '#161b22', border: '1px solid #30363d', borderRadius: 10, padding: '6px 8px' }}>
      {groups.map(g => (
        <div key={g.gi}>
          <div style={{ fontSize: 11, color: '#8b949e', textTransform: 'uppercase', letterSpacing: '.04em', padding: '8px 6px 3px' }}>{g.title}</div>
          {g.items.map(c => (
            <div key={c.time} style={{
              display: 'flex', gap: 8, alignItems: 'center', padding: '4px 6px', borderRadius: 8,
              background: c === active ? '#1f6feb1f' : 'transparent', cursor: 'pointer',
            }}>
              <input type="checkbox" checked={checked.has(c.time)} onChange={() => toggle(c.time)}
                onClick={e => e.stopPropagation()} style={{ accentColor: '#2f81f7' }} />
              <span onClick={() => onPick(c)} style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, minWidth: 0 }}>
                <button onClick={e => { e.stopPropagation(); onPick(c) }} style={chip}>{fmt(c.time)}</button>
                <span style={{ fontSize: 12, width: 16, textAlign: 'center', color: '#8b949e' }}>{TYPE_ICON[c.widget] ?? '·'}</span>
                <span style={{ fontSize: 13, color: c === active ? '#e6edf3' : '#c9d1d9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.title}{c.user_made ? ' ✦' : ''}
                </span>
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Transcript({ cues, chapters, time, seek, onAsk }) {
  const box = useRef(null)
  const [pinned, setPinned] = useState(true) // auto-follow playback

  // group cues into YouTube-style rows: [mm:ss chip] text — break at chapter bounds
  const rows = useMemo(() => {
    const bounds = chapters.map(c => c.start)
    const out = []
    let cur = null, nextBound = 0
    cues.forEach((c, i) => {
      while (nextBound < bounds.length && c.start >= bounds[nextBound]) nextBound++
      const chIdx = nextBound - 1
      if (!cur || cur.len > 150 || cur.ch !== chIdx) {
        cur = { start: c.start, ch: chIdx, len: 0, parts: [] }
        out.push(cur)
      }
      cur.parts.push({ i, text: c.text })
      cur.len += c.text.length + 1
    })
    return out
  }, [cues, chapters])

  const activeRow = useMemo(() => {
    let lo = 0, hi = rows.length - 1, ans = 0
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (rows[mid].start <= time) { ans = mid; lo = mid + 1 } else hi = mid - 1
    }
    return ans
  }, [rows, time])

  const [from, to] = [Math.max(0, activeRow - 60), Math.min(rows.length, activeRow + 120)]

  useEffect(() => {
    if (!pinned) return
    box.current?.querySelector(`[data-r="${activeRow}"]`)
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [activeRow, pinned])

  const onMouseUp = () => {
    const sel = window.getSelection()
    const text = sel?.toString().trim()
    if (!text || text.length < 4) return
    const node = sel.anchorNode?.parentElement?.closest('[data-i]')
    const i = node ? parseInt(node.dataset.i, 10) : null
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    setPinned(false)
    onAsk({ text, time: i != null ? cues[i].start : time, x: rect.left + rect.width / 2, y: rect.bottom })
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '10px 0 6px' }}>
        <span style={{ fontSize: 12, color: '#8b949e' }}>
          transcript — <b style={{ color: '#e6edf3' }}>select any passage</b> to turn that moment into a widget
        </span>
        {!pinned && (
          <button onClick={() => setPinned(true)} style={{
            background: 'none', border: '1px solid #30363d', color: '#2f81f7',
            borderRadius: 6, fontSize: 11, padding: '2px 8px',
          }}>↓ follow video</button>
        )}
      </div>
      {chapters.length > 0 && <Chapters chapters={chapters} time={time} seek={seek} />}
      <div ref={box} onMouseUp={onMouseUp} onWheel={() => setPinned(false)} style={{
        maxHeight: 300, overflowY: 'auto', background: '#161b22', border: '1px solid #30363d',
        borderRadius: 10, padding: '8px 10px',
      }}>
        {rows.slice(from, to).map((r, j) => {
          const ri = from + j
          const isActive = ri === activeRow
          return (
            <div key={r.start} data-r={ri} style={{
              display: 'flex', gap: 10, alignItems: 'flex-start', padding: '5px 6px',
              borderRadius: 8, background: isActive ? '#1f6feb1f' : 'transparent',
            }}>
              <button onClick={() => seek(r.start)} style={chip}>{fmt(r.start)}</button>
              <span style={{ fontSize: 13.5, lineHeight: 1.65, color: isActive ? '#e6edf3' : '#c9d1d9' }}>
                {r.parts.map(p => (
                  <span key={p.i} data-i={p.i}>{p.text}{' '}</span>
                ))}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// click-the-whiteboard: drag a box on the video, that region comes alive
function TouchOverlay({ onRegion, busy }) {
  const box = useRef(null)
  const dragRef = useRef(null) // {x0,y0,x1,y1} normalized — ref: updates synchronously
  const [, force] = useState(0)
  const rerender = () => force(n => n + 1)

  const norm = (e) => {
    const r = box.current.getBoundingClientRect()
    return [
      Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1),
      Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1),
    ]
  }
  const down = (e) => {
    const [x, y] = norm(e)
    dragRef.current = { x0: x, y0: y, x1: x, y1: y }
    rerender()
  }
  const move = (e) => {
    if (!dragRef.current || busy) return
    const [x, y] = norm(e)
    dragRef.current = { ...dragRef.current, x1: x, y1: y }
    rerender()
  }
  const up = () => {
    const d = dragRef.current
    if (!d) return
    const rect = {
      x: Math.min(d.x0, d.x1),
      y: Math.min(d.y0, d.y1),
      w: Math.abs(d.x1 - d.x0),
      h: Math.abs(d.y1 - d.y0),
    }
    if (rect.w < 0.03 || rect.h < 0.03) { dragRef.current = null; rerender(); return }
    onRegion(rect, () => { dragRef.current = null; rerender() })
  }
  const drag = dragRef.current
  const sel = drag && {
    left: `${Math.min(drag.x0, drag.x1) * 100}%`,
    top: `${Math.min(drag.y0, drag.y1) * 100}%`,
    width: `${Math.abs(drag.x1 - drag.x0) * 100}%`,
    height: `${Math.abs(drag.y1 - drag.y0) * 100}%`,
  }
  return (
    <div ref={box} onMouseDown={down} onMouseMove={move} onMouseUp={up}
      style={{ position: 'absolute', inset: 0, zIndex: 5, cursor: 'crosshair', background: 'rgba(13,17,23,.25)' }}>
      <div style={{
        position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)',
        background: '#161b22ee', border: '1px solid #388bfd66', color: '#e6edf3',
        borderRadius: 999, padding: '4px 14px', fontSize: 12, pointerEvents: 'none', whiteSpace: 'nowrap',
      }}>
        {busy ? '⚡ bringing that drawing to life…' : 'drag a box around any drawing, equation or number'}
      </div>
      {sel && (
        <div style={{
          position: 'absolute', ...sel, border: '2px solid #2f81f7', background: '#2f81f722',
          borderRadius: 6, boxShadow: busy ? '0 0 24px #2f81f7aa' : 'none',
          animation: busy ? 'pulse 1.2s infinite' : 'none', pointerEvents: 'none',
        }} />
      )}
    </div>
  )
}

function GlobalAsk({ onAsk, busy, concepts, time }) {
  const [q, setQ] = useState('')
  const upcoming = concepts.find(c => c.time > time)
  const suggestions = [
    'make a calculator from this moment',
    'explain what\'s on screen right now',
    'what would change if I doubled the main number?',
    ...(upcoming ? [`preview: ${upcoming.title.slice(0, 36)}…`] : []),
  ]
  const go = (text) => { if (text.trim()) { onAsk(text.trim()); setQ('') } }
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px',
      background: '#161b22', border: '1px solid #30363d', borderRadius: 12,
    }}>
      <div style={{ display: 'flex', gap: 8 }}>
        <input value={q} placeholder="⚡ ask this lecture anything — a widget appears"
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && go(q)}
          style={{
            flex: 1, background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
            borderRadius: 8, padding: '9px 12px', fontSize: 13, textAlign: 'left',
          }} />
        <button disabled={busy} onClick={() => go(q)} style={{
          background: busy ? '#30363d' : '#2f81f7', color: 'white', border: 'none',
          borderRadius: 8, padding: '8px 14px', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
        }}>{busy ? 'reading…' : 'ask'}</button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {suggestions.map(s => (
          <button key={s} disabled={busy} onClick={() => go(s.startsWith('preview:') ? `make the upcoming concept interactive: ${upcoming.title}` : s)} style={{
            background: 'none', border: '1px solid #30363d', color: '#8b949e',
            borderRadius: 999, padding: '3px 10px', fontSize: 11.5,
          }}>{s}</button>
        ))}
      </div>
    </div>
  )
}

function AskBox({ ask, onClose, onCreate, busy }) {
  const [intent, setIntent] = useState('')
  return (
    <div style={{
      position: 'fixed', left: Math.max(12, Math.min(ask.x - 190, window.innerWidth - 400)),
      top: Math.min(ask.y + 10, window.innerHeight - 220),
      width: 380, zIndex: 9, background: '#1c2128', border: '1px solid #388bfd66',
      borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 10,
      boxShadow: '0 8px 30px rgba(0,0,0,.5)',
    }}>
      <div style={{ fontSize: 12, color: '#8b949e', fontStyle: 'italic' }}>
        “{ask.text.slice(0, 140)}{ask.text.length > 140 ? '…' : ''}”
      </div>
      <input autoFocus value={intent} placeholder="what do you want to play with? (optional)"
        onChange={e => setIntent(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') onCreate(intent); if (e.key === 'Escape') onClose() }}
        style={{
          width: '100%', background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
          borderRadius: 8, padding: '9px 10px', fontSize: 13, textAlign: 'left',
        }} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 13 }}>cancel</button>
        <button disabled={busy} onClick={() => onCreate(intent)} style={{
          background: busy ? '#30363d' : '#2f81f7', color: 'white', border: 'none',
          borderRadius: 8, padding: '8px 16px', fontSize: 13, fontWeight: 600,
        }}>{busy ? 'reading that moment…' : '⚡ make it interactive'}</button>
      </div>
    </div>
  )
}

function Lecture({ videoId, role }) {
  const roleCfg = ROLES[role]
  const [concepts, setConcepts] = useState([])
  const [cues, setCues] = useState([])
  const [chapters, setChapters] = useState([])
  const [selected, setSelected] = useState(null)
  const [followVideo, setFollowVideo] = useState(true)
  const [duration, setDuration] = useState(7200)
  const [shareUrl, setShareUrl] = useState(null)
  const [ask, setAsk] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const [engine, setEngine] = useState(null)
  const [tab, setTab] = useState(roleCfg?.tab ?? 'transcript')
  const [checked, setChecked] = useState(new Set())
  const [touchMode, setTouchMode] = useState(false)
  const liveParams = useRef(null)
  const { holder, time, seek } = useYouTube(videoId)
  const ingested = INGESTED.includes(videoId)

  useEffect(() => {
    fetch('/api/info').then(r => r.json()).then(setEngine).catch(() => setEngine(null))
  }, [])

  useEffect(() => {
    const remix = specFromHash()
    if (remix) { setSelected(remix); setFollowVideo(false) }
    if (!ingested) return
    fetch(`/${videoId}/concepts.json`).then(r => r.json()).then(cs => {
      setConcepts(cs)
      if (cs.length) setDuration(Math.max(...cs.map(c => c.time)) * 1.08)
    }).catch(() => setConcepts([]))
    fetch(`/${videoId}/transcript.json`).then(r => r.json()).then(setCues).catch(() => setCues([]))
    fetch(`/${videoId}/chapters.json`).then(r => r.json()).then(setChapters).catch(() => setChapters([]))
  }, [ingested, videoId])

  const pinnedUntil = useRef(0)
  useEffect(() => {
    if (!followVideo || Date.now() < pinnedUntil.current) return
    const live = [...concepts].reverse().find(c => time >= c.time && time < c.time + 90)
    if (live && live !== selected) { setSelected(live); liveParams.current = null }
  }, [time, concepts, followVideo]) // eslint-disable-line react-hooks/exhaustive-deps

  const onState = useCallback((p) => { liveParams.current = p }, [])

  const share = () => {
    if (!selected) return
    const spec = { ...selected, params: liveParams.current ?? selected.params }
    setShareUrl(`${location.origin}${location.pathname}#s=${b64enc(spec)}`)
  }

  const askRegion = async (rect, done) => {
    setBusy(true)
    try {
      const iframe = document.querySelector('#player-box iframe')
      iframe?.contentWindow?.postMessage(JSON.stringify({ event: 'command', func: 'pauseVideo', args: '' }), '*')
      const around = cues.filter(c => Math.abs(c.start - time) < 35).map(c => c.text).join(' ')
      const r = await fetch('/api/region', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: around, time, ...rect, video: videoId }),
      })
      const spec = await r.json()
      if (spec.error) { setToast(`couldn't read that region: ${spec.error}`); return }
      if (spec.answer) {
        setSelected({ widget: 'answer', title: 'about that region', explanation: spec.answer, time: spec.time, user_made: true })
      } else {
        setConcepts(cs => [...cs, spec].sort((a, b) => a.time - b.time))
        setSelected(spec)
      }
      setFollowVideo(false)
      setTouchMode(false)
    } catch {
      setToast('ask endpoint offline — run: uv run serve.py')
    } finally {
      setBusy(false)
      done?.()
      setTimeout(() => setToast(null), 4000)
    }
  }

  const askGlobal = async (question) => {
    setBusy(true)
    try {
      const around = cues.filter(c => Math.abs(c.start - time) < 35).map(c => c.text).join(' ')
      const r = await fetch('/api/widget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: around || question, time, ask: question, video: videoId }),
      })
      const spec = await r.json()
      if (spec.error) { setToast(`no luck: ${spec.error}`); return }
      if (spec.answer) {
        setSelected({ widget: 'answer', title: question, explanation: spec.answer, time: spec.time, user_made: true })
        setFollowVideo(false)
        return
      }
      setConcepts(cs => [...cs, spec].sort((a, b) => a.time - b.time))
      setSelected(spec)
      setFollowVideo(false)
    } catch {
      setToast('ask endpoint offline — run: uv run serve.py')
    } finally {
      setBusy(false)
      setTimeout(() => setToast(null), 4000)
    }
  }

  const createWidget = async (intent) => {
    setBusy(true)
    try {
      const r = await fetch('/api/widget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ask.text, time: ask.time, ask: intent, video: videoId }),
      })
      const spec = await r.json()
      if (spec.error) { setToast(`couldn't map that moment: ${spec.error}`); return }
      setConcepts(cs => [...cs, spec].sort((a, b) => a.time - b.time))
      setSelected(spec)
      setFollowVideo(false)
      setAsk(null)
    } catch {
      setToast('ask endpoint offline — run: uv run serve.py')
    } finally {
      setBusy(false)
      setTimeout(() => setToast(null), 4000)
    }
  }

  const active = selected
  const Widget = active ? WIDGETS[active.widget] : null

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <header style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <a href="/" title="back to start" style={{ textDecoration: 'none', color: '#e6edf3' }}>
          <h1 style={{ fontSize: 22, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#8b949e', fontSize: 15 }}>←</span> 8kEdu
          </h1>
        </a>
        <span style={{ color: '#8b949e', fontSize: 14 }}>YouTube video → interactive learning dashboard</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {roleCfg && (
            <span style={{ fontSize: 11.5, color: '#d2a8ff', border: '1px solid #8957e555', borderRadius: 999, padding: '3px 10px', whiteSpace: 'nowrap' }}>
              {roleCfg.icon} {roleCfg.label}
            </span>
          )}
          <span style={{ fontSize: 11.5, color: '#8b949e', border: '1px solid #30363d', borderRadius: 999, padding: '3px 10px', whiteSpace: 'nowrap' }}>
            {engine
              ? <>{engine.mode === 'local' ? '🖥 local' : '🔑 byok'} · {String(engine.model).replace('mlx-community/', '').slice(0, 34)}</>
              : '⚪ engine offline'}
          </span>
        </span>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: 14, alignItems: 'start' }}>
        <div style={{ minWidth: 0 }}>
          <div id="player-box" style={{ borderRadius: 12, overflow: 'hidden', border: touchMode ? '1px solid #388bfd' : '1px solid #30363d' }}>
            <div ref={holder} />
            {touchMode && <TouchOverlay onRegion={askRegion} busy={busy} />}
            <button onClick={() => setTouchMode(m => !m)} style={{
              position: 'absolute', right: 10, bottom: 10, zIndex: 6,
              background: touchMode ? '#2f81f7' : '#161b22dd', color: touchMode ? 'white' : '#e6edf3',
              border: '1px solid #388bfd66', borderRadius: 999, padding: '6px 14px',
              fontSize: 12.5, fontWeight: 600,
            }}>{touchMode ? '✕ done' : '🎯 touch the screen'}</button>
          </div>

          <div style={{ position: 'relative', height: 30, marginTop: 10, background: 'linear-gradient(180deg, #161b22, #10141a)', borderRadius: 999, border: '1px solid #30363d', overflow: 'hidden' }}>
            {/* chapter shading for rhythm */}
            {chapters.map((ch, i) => i % 2 === 1 && (
              <div key={i} style={{
                position: 'absolute', top: 0, bottom: 0,
                left: `${(ch.start / duration) * 100}%`,
                width: `${(((ch.end ?? duration) - ch.start) / duration) * 100}%`,
                background: '#ffffff05',
              }} />
            ))}
            {concepts.map((c, i) => {
              const isActive = c === active
              return (
                <button key={i} title={`${c.title} · ${TYPE_ICON[c.widget] ?? ''}`} className="tl-tick"
                  onClick={() => { setSelected(c); liveParams.current = null; setFollowVideo(true); pinnedUntil.current = Date.now() + 60000; seek(c.time) }}
                  style={{
                    position: 'absolute', left: `calc(${(c.time / duration) * 100}% - 2px)`,
                    top: '50%', width: 4, border: 'none', padding: 0, borderRadius: 99,
                    height: isActive ? 22 : c.user_made ? 18 : 13,
                    background: c.user_made ? '#e3b341' : (TYPE_COLOR[c.widget] ?? '#6e7681'),
                    opacity: isActive ? 1 : 0.65,
                    transform: 'translateY(-50%)',
                    boxShadow: isActive ? `0 0 10px ${TYPE_COLOR[c.widget] ?? '#2f81f7'}` : 'none',
                    transition: 'height .15s, opacity .15s',
                  }} />
              )
            })}
            {/* playhead */}
            <div style={{ position: 'absolute', left: `calc(${(time / duration) * 100}% - 1px)`, top: 0, bottom: 0, width: 2, background: '#f85149', boxShadow: '0 0 6px #f8514988' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            {['transcript', 'moments'].map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                background: tab === t ? '#1f6feb33' : 'none',
                border: `1px solid ${tab === t ? '#388bfd66' : '#30363d'}`,
                color: tab === t ? '#e6edf3' : '#8b949e',
                borderRadius: 8, padding: '4px 12px', fontSize: 12.5,
              }}>{t === 'moments' ? `☰ moments (${concepts.length})` : 'transcript'}</button>
            ))}
            <span style={{ color: '#8b949e', fontSize: 11.5, marginLeft: 'auto' }}>gold ✦ = made by a viewer</span>
          </div>

          {checked.size > 0 && (
            <div style={{
              display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0 0', padding: '8px 10px',
              background: '#1f6feb14', border: '1px solid #388bfd44', borderRadius: 10, flexWrap: 'wrap',
            }}>
              <span style={{ fontSize: 12.5, color: '#e6edf3' }}>{checked.size} selected →</span>
              {[
                ['📓 notebook', () => download('educlaw-notes.ipynb',
                  buildNotebook(concepts.filter(c => checked.has(c.time)), videoId, 'Interactive lecture notes'), 'application/json')],
                ['📝 markdown', () => download('educlaw-notes.md',
                  buildMarkdown(concepts.filter(c => checked.has(c.time)), videoId, 'Interactive lecture notes', location.origin), 'text/markdown')],
                ['🖥 deck / pdf', () => {
                  const html = buildDeckHtml(concepts.filter(c => checked.has(c.time)), videoId, 'Interactive lecture notes')
                  window.open(URL.createObjectURL(new Blob([html], { type: 'text/html' })), '_blank')
                }],
              ].sort(([a], [b]) =>
                (b === roleCfg?.primary ? 1 : 0) - (a === roleCfg?.primary ? 1 : 0)
              ).map(([label, fn]) => {
                const isPrimary = !roleCfg || label === roleCfg.primary
                return (
                  <button key={label} onClick={fn} style={{
                    background: isPrimary ? '#2f81f7' : 'none',
                    color: isPrimary ? 'white' : '#8b949e',
                    border: isPrimary ? 'none' : '1px solid #30363d',
                    borderRadius: 8, padding: '6px 12px', fontSize: 12.5, fontWeight: 600,
                  }}>{label}</button>
                )
              })}
              <button onClick={() => setChecked(new Set())} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 12 }}>clear</button>
            </div>
          )}
          {role === 'researcher' && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#8b949e', border: '1px dashed #30363d', borderRadius: 10, padding: '8px 12px' }}>
              🔬 researcher gateway — coming soon: trace a concept across lectures (cross-video graph), citation export, side-by-side sources
            </div>
          )}

          <div style={{ marginTop: 8 }}>
            {tab === 'moments' ? (
              <Moments concepts={concepts} chapters={chapters} active={selected}
                checked={checked} setChecked={setChecked}
                onPick={(c) => { setSelected(c); liveParams.current = null; setFollowVideo(true); pinnedUntil.current = Date.now() + 60000; seek(c.time) }} />
            ) : cues.length > 0 ? (
              <Transcript cues={cues} chapters={chapters} time={time} seek={seek} onAsk={setAsk} />
            ) : null}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          {ingested && <GlobalAsk onAsk={askGlobal} busy={busy} concepts={concepts} time={time} />}
          {active ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{active.title}</div>
                  <div style={{ fontSize: 13, color: '#8b949e', marginTop: 4 }}>{active.explanation}</div>
                </div>
                <button onClick={share} style={{
                  background: '#238636', color: 'white', border: 'none', borderRadius: 8,
                  padding: '8px 14px', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                }}>share remix</button>
              </div>
              {Widget ? <Widget key={`${active.time}-${active.widget}`} params={active.params ?? {}} onState={onState} /> : null}
              <div style={{ fontSize: 11, color: '#8b949e' }}>
                {followVideo
                  ? <>extracted at {Math.floor((active.time ?? 0) / 60)}:{String(Math.floor((active.time ?? 0) % 60)).padStart(2, '0')} · {active.user_made ? 'asked for by a viewer' : 'spec by VLM'} · rendered live</>
                  : active.user_made
                    ? <>made from your selection · <button onClick={() => setFollowVideo(true)} style={{ background: 'none', border: 'none', color: '#2f81f7', fontSize: 11, padding: 0, textDecoration: 'underline' }}>back to the lecture</button></>
                    : <>remixed spec — loaded from the link · <button onClick={() => setFollowVideo(true)} style={{ background: 'none', border: 'none', color: '#2f81f7', fontSize: 11, padding: 0, textDecoration: 'underline' }}>back to the lecture</button></>}
              </div>
            </>
          ) : (
            <div style={{ color: '#8b949e', fontSize: 14, padding: 30, textAlign: 'center', border: '1px dashed #30363d', borderRadius: 12 }}>
              play the lecture — or select a transcript passage and ask for the widget you want
            </div>
          )}
        </div>
      </div>

      {ask && <AskBox ask={ask} busy={busy} onClose={() => setAsk(null)} onCreate={createWidget} />}
      {shareUrl && <ShareModal url={shareUrl} onClose={() => setShareUrl(null)} />}
      {!ingested && (
        <div style={{ color: '#d29922', fontSize: 13, border: '1px solid #d2992255', borderRadius: 10, padding: '10px 14px' }}>
          this video isn't analyzed yet — run <code>uv run ingest.py "&lt;url&gt;" && uv run analyze.py</code> to mint its widgets
        </div>
      )}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)',
          background: '#3d1e1e', border: '1px solid #f85149', color: '#ffa198',
          borderRadius: 10, padding: '10px 18px', fontSize: 13, zIndex: 11,
        }}>{toast}</div>
      )}
    </div>
  )
}

// theme tokens — light + dark
const THEMES = {
  dark: { bg: 'radial-gradient(1200px 600px at 50% -10%, #10160c 0%, #0a0d08 55%, #080a06 100%)',
    solid: '#0a0d08', panel: '#0f140b', text: '#f2f6ec', sub: '#cbd6c0', muted: '#8b9682',
    faint: '#66735b', line: '#2b3a1e', acc: '#7bd33f', accText: '#0a0d08', dim720: '#5a6a4e', field: false },
  light: { bg: 'radial-gradient(1200px 600px at 50% -10%, #eef4e6 0%, #f5f8f1 55%, #f7faf3 100%)',
    solid: '#f5f8f1', panel: '#ffffff', text: '#14180f', sub: '#39452f', muted: '#5c6b50',
    faint: '#8a9880', line: '#dbe4d1', acc: '#3f8f18', accText: '#ffffff', dim720: '#a7b39a', field: true },
}

// ambient attention-field — the app's own widget, alive, reacting to the cursor
function AttentionField({ light = false }) {
  const ref = useRef(null)
  useEffect(() => {
    const cv = ref.current, ctx = cv.getContext('2d')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf, t = 0, mx = -999, my = -999, w = 0, h = 0, cols = 0, rows = 0
    const GAP = 6, CELL = 26
    const resize = () => {
      const r = cv.parentElement.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = r.width; h = r.height
      cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + 'px'; cv.style.height = h + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      cols = Math.ceil(w / (CELL + GAP)) + 1; rows = Math.ceil(h / (CELL + GAP)) + 1
    }
    resize(); window.addEventListener('resize', resize)
    const onMove = e => { const r = cv.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top }
    const onLeave = () => { mx = -999; my = -999 }
    cv.parentElement.addEventListener('pointermove', onMove)
    cv.parentElement.addEventListener('pointerleave', onLeave)
    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
        const x = i * (CELL + GAP), y = j * (CELL + GAP)
        let v = 0.5 + 0.5 * Math.sin(t * 0.9 + i * 0.55 + j * 0.4 + Math.sin(t * 0.3 + j))
        v *= 0.35
        const dx = x + CELL / 2 - mx, dy = y + CELL / 2 - my
        const glow = Math.exp(-(dx * dx + dy * dy) / 9000)
        const lit = Math.min(1, v + glow * 0.95)
        if (light) {
          const g = Math.round(150 - lit * 60), rr = Math.round(120 - lit * 90), b = Math.round(110 - lit * 90)
          ctx.fillStyle = `rgba(${rr},${g},${b},${0.05 + lit * 0.5})`
        } else {
          const g = Math.round(90 + lit * 150), rr = Math.round(20 + lit * 40), b = Math.round(15 + lit * 40)
          ctx.fillStyle = `rgba(${rr},${g},${b},${0.10 + lit * 0.82})`
        }
        const s = CELL * (0.62 + lit * 0.38), o = (CELL - s) / 2
        ctx.beginPath(); ctx.roundRect(x + o, y + o, s, s, 5); ctx.fill()
      }
      t += 0.016
      raf = requestAnimationFrame(draw)
    }
    if (reduced) { t = 2; draw(); cancelAnimationFrame(raf) } else draw()
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize)
      cv.parentElement.removeEventListener('pointermove', onMove); cv.parentElement.removeEventListener('pointerleave', onLeave) }
  }, [light])
  return <canvas ref={ref} style={{ position: 'absolute', inset: 0, display: 'block' }} aria-hidden="true" />
}

function LandingStyles({ acc }) {
  return <style>{`
    @keyframes eduGlow{0%,100%{opacity:.55}50%{opacity:1}}
    .edu-card{transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
    .edu-card:hover{transform:translateY(-3px);border-color:${acc}99;box-shadow:0 12px 34px -14px ${acc}66}
    .edu-open{transition:transform .12s ease,filter .18s ease}
    .edu-open:hover{filter:brightness(1.06)}.edu-open:active{transform:scale(.97)}
    .edu-in:focus{outline:2px solid ${acc};outline-offset:1px}
    .edu-pulse{animation:eduGlow 2.4s ease-in-out infinite}
    @media (prefers-reduced-motion:reduce){.edu-pulse{animation:none}}
  `}</style>
}

// 8kEdu mark — a pixel grid that "upscales": dim/sparse corner → bright/dense corner (720p → 8K)
function Logo({ size = 40, wordColor = '#f2f6ec' }) {
  const N = 4, gap = size * 0.14, cell = (size - gap * (N - 1)) / N
  const cells = []
  for (let r = 0; r < N; r++) for (let c = 0; c < N; c++)
    cells.push({ r, c, lit: (r + c) / (2 * (N - 1)), i: r * N + c })
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.32 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label="8kEdu logo">
        {cells.map(({ r, c, lit, i }) => (
          <motion.rect key={i}
            x={c * (cell + gap)} y={r * (cell + gap)} width={cell} height={cell} rx={cell * 0.28}
            fill={`rgb(${Math.round(30 + lit * 90)},${Math.round(70 + lit * 140)},${Math.round(25 + lit * 50)})`}
            initial={{ opacity: 0, scale: 0.3 }} animate={{ opacity: 0.4 + lit * 0.6, scale: 1 }}
            transition={{ delay: 0.15 + lit * 0.5, type: 'spring', stiffness: 260, damping: 18 }} />
        ))}
      </svg>
      <span style={{ fontSize: size * 0.7, fontWeight: 800, letterSpacing: '-.03em', color: wordColor }}>
        <span style={{ color: '#63b524' }}>8k</span>Edu
      </span>
    </span>
  )
}

// ————— the "drop a lecture → artifacts burst out" showcase —————
// Every card is a hand-drawn mini-render of a REAL artifact (real code, real numbers,
// real frames from the lecture) — not an icon.

const mono = 'ui-monospace,SFMono-Regular,Menlo,monospace'
const cardBase = { width: 196, height: 162, borderRadius: 14, overflow: 'hidden', flexShrink: 0, position: 'relative', boxShadow: '0 18px 40px -18px rgba(0,0,0,.55)' }
const Badge = ({ children, color = '#7bd33f' }) => (
  <span style={{ position: 'absolute', top: 8, left: 8, zIndex: 2, fontFamily: mono, fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', background: '#0a0d08d9', color, borderRadius: 5, padding: '3px 7px' }}>{children}</span>
)

const NotebookCard = () => (
  <div style={{ ...cardBase, background: '#0d1117', border: '1px solid #26302a' }}>
    <Badge>notebook</Badge>
    <div style={{ display: 'flex', gap: 4, padding: '9px 10px 6px', justifyContent: 'flex-end' }}>
      {['#ff5f57', '#febc2e', '#28c840'].map(c => <span key={c} style={{ width: 7, height: 7, borderRadius: 4, background: c }} />)}
    </div>
    <pre style={{ margin: 0, padding: '2px 12px', fontFamily: mono, fontSize: 8.5, lineHeight: 1.55 }}>
      <span style={{ color: '#ff7b72' }}>import</span><span style={{ color: '#c9d1d9' }}> numpy </span><span style={{ color: '#ff7b72' }}>as</span><span style={{ color: '#c9d1d9' }}> np{'\n'}</span>
      <span style={{ color: '#c9d1d9' }}>T = </span><span style={{ color: '#79c0ff' }}>8{'\n'}</span>
      <span style={{ color: '#c9d1d9' }}>tril = np.tril(np.ones((T,T))){'\n'}</span>
      <span style={{ color: '#c9d1d9' }}>wei = tril / tril.</span><span style={{ color: '#d2a8ff' }}>sum</span><span style={{ color: '#c9d1d9' }}>(1)</span>
    </pre>
    <div style={{ margin: '6px 12px', padding: '6px 8px', background: '#010409', borderRadius: 7, fontFamily: mono, fontSize: 8, color: '#7ee787', lineHeight: 1.5 }}>
      [[1.  0.  0. ]{'\n'} [0.5 0.5 0. ]{'\n'} [0.33 0.33 0.33]]
    </div>
    <div style={{ position: 'absolute', right: 12, bottom: 10, display: 'flex', alignItems: 'flex-end', gap: 3, height: 26 }}>
      {[10, 16, 22, 26].map((h, i) => <span key={i} style={{ width: 9, height: h, background: `rgba(126,231,135,${.4 + i * .15})`, borderRadius: 2 }} />)}
    </div>
  </div>
)

const MindmapCard = () => (
  <div style={{ ...cardBase, background: '#0c130f', border: '1px solid #26302a' }}>
    <Badge>mind map</Badge>
    <svg viewBox="0 0 216 172" style={{ width: '100%', height: '100%' }}>
      {[
        'M108,88 C88,70 70,62 50,54', 'M108,88 C128,68 148,60 168,50',
        'M108,88 C84,108 66,116 46,124', 'M108,88 C132,110 152,118 172,126', 'M108,88 C110,58 110,44 108,30',
      ].map((d, i) => <path key={i} d={d} stroke="#3f5a33" strokeWidth="1.4" fill="none" />)}
      {[
        [108, 88, 'attention', '#8ee23e', '#12240c'],
        [50, 50, 'queries', '#c9d1d9', '#161d18'], [170, 46, 'keys', '#c9d1d9', '#161d18'],
        [44, 128, 'values', '#c9d1d9', '#161d18'], [174, 130, 'softmax', '#c9d1d9', '#161d18'], [108, 26, 'heads ×8', '#c9d1d9', '#161d18'],
      ].map(([x, y, t, fg, bgc], i) => (
        <g key={i}>
          <rect x={x - (i === 0 ? 34 : 26)} y={y - 11} width={i === 0 ? 68 : 52} height={22} rx={11} fill={bgc} stroke={i === 0 ? '#8ee23e' : '#2c3a2e'} strokeWidth={i === 0 ? 1.4 : 1} />
          <text x={x} y={y + 3.5} textAnchor="middle" fontFamily={mono} fontSize={i === 0 ? 10 : 9} fill={fg} fontWeight={i === 0 ? 700 : 400}>{t}</text>
        </g>
      ))}
    </svg>
  </div>
)

const FlashcardCard = () => (
  <div style={{ ...cardBase, background: 'linear-gradient(160deg,#182013,#0e1410)', border: '1px solid #26302a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <Badge>flashcards</Badge>
    <div style={{ position: 'absolute', width: 158, height: 104, borderRadius: 10, background: '#e8e4d5', transform: 'rotate(6deg) translate(10px,8px)' }} />
    <div style={{ position: 'relative', width: 162, height: 108, borderRadius: 10, background: '#f7f4e9', transform: 'rotate(-2.5deg)', padding: '12px 14px', boxShadow: '0 8px 18px -8px rgba(0,0,0,.5)' }}>
      <div style={{ fontFamily: mono, fontSize: 8.5, color: '#8a8467', letterSpacing: '.1em' }}>CARD 12 / 55</div>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: '#1d2416', lineHeight: 1.35, marginTop: 6 }}>
        What does temperature do to softmax?
      </div>
      <div style={{ position: 'absolute', bottom: 10, right: 14, fontFamily: mono, fontSize: 9, color: '#5c9500', fontWeight: 700 }}>flip ›</div>
    </div>
  </div>
)

const ChartCard = () => (
  <div style={{ ...cardBase, background: '#fbfdf8', border: '1px solid #d7e0cc' }}>
    <Badge color="#3f8f18">charts</Badge>
    <svg viewBox="0 0 216 172" style={{ width: '100%', height: '100%' }}>
      {[40, 72, 104, 136].map(y => <line key={y} x1="26" y1={y} x2="200" y2={y} stroke="#e4ebdb" strokeWidth="1" />)}
      {[54, 92, 130, 168].map((x, i) => <rect key={x} x={x} y={140 - [26, 52, 34, 66][i]} width="18" height={[26, 52, 34, 66][i]} rx="3" fill="#bfe39b" />)}
      <path d="M28,132 C70,132 84,128 104,104 C124,80 150,48 198,38" stroke="#3f8f18" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <circle cx="198" cy="38" r="4" fill="#3f8f18" />
      <text x="30" y="160" fontFamily={mono} fontSize="9.5" fill="#7c8a6e">GELU(x) · from 106:38</text>
    </svg>
  </div>
)

const DashboardCard = () => (
  <div style={{ ...cardBase, background: '#0b0f14', border: '1px solid #26302a' }}>
    <Badge>dashboard</Badge>
    <div style={{ display: 'flex', gap: 7, padding: '28px 10px 0' }}>
      <div style={{ flex: 1.25 }}>
        <img src="/kCc8FmEb1nY/frames/f_003780.jpg" alt="" style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', borderRadius: 6, border: '1px solid #22292f' }} />
        <div style={{ position: 'relative', height: 10, background: '#141a21', borderRadius: 5, marginTop: 6 }}>
          {[12, 25, 38, 55, 63, 78, 90].map((p, i) => (
            <span key={p} style={{ position: 'absolute', left: `${p}%`, top: 2, width: 3, height: 6, borderRadius: 2, background: ['#b48eff', '#ffab70', '#79c0ff', '#56d364', '#79c0ff', '#ff9bce', '#e3b341'][i] }} />
          ))}
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 3 }}>
          {[0.9, 0.2, 0.15, 0.5, 0.95, 0.3, 0.25, 0.6, 0.85].map((v, i) => (
            <span key={i} style={{ aspectRatio: '1', borderRadius: 3, background: `rgba(123,211,63,${v})` }} />
          ))}
        </div>
        <div style={{ height: 5, background: '#141a21', borderRadius: 3, marginTop: 8, position: 'relative' }}>
          <span style={{ position: 'absolute', left: '58%', top: -3, width: 11, height: 11, borderRadius: 6, background: '#7bd33f' }} />
        </div>
        <div style={{ fontFamily: mono, fontSize: 7.5, color: '#5d6b78', marginTop: 7 }}>T = 1.85 · live</div>
      </div>
    </div>
    <div style={{ position: 'absolute', bottom: 9, left: 10, fontFamily: mono, fontSize: 8, color: '#56d364' }}>55 touchable moments</div>
  </div>
)

const SheetCard = () => (
  <div style={{ ...cardBase, background: '#ffffff', border: '1px solid #d7e0cc' }}>
    <Badge color="#3f8f18">sheets</Badge>
    <table style={{ width: '100%', marginTop: 26, borderCollapse: 'collapse', fontFamily: mono, fontSize: 8.5 }}>
      <thead><tr style={{ background: '#eef4e6' }}>
        {['', 'A', 'B', 'C'].map(h => <th key={h} style={{ border: '1px solid #e0e8d6', padding: '3px 6px', color: '#7c8a6e', fontWeight: 600 }}>{h}</th>)}
      </tr></thead>
      <tbody>
        {[['1', 'home price', '$300,000', ''], ['2', 'down', '10%', '$30,000'], ['3', 'rate', '6.5%', ''], ['4', 'PMI / mo', '$112.50', '⚠'], ['5', 'payment', '$1,908.82', '✓']].map(r => (
          <tr key={r[0]}>{r.map((c, j) => (
            <td key={j} style={{ border: '1px solid #e8eee0', padding: '3px 6px', color: j === 0 ? '#a9b59c' : c.startsWith('$1,9') ? '#3f8f18' : '#333d2b', fontWeight: c.startsWith('$1,9') ? 700 : 400, background: j === 0 ? '#f6f9f1' : '#fff' }}>{c}</td>
          ))}</tr>
        ))}
      </tbody>
    </table>
  </div>
)

const SlidesCard = () => (
  <div style={{ ...cardBase, background: '#10150f', border: '1px solid #26302a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <Badge>slides</Badge>
    <div style={{ position: 'absolute', width: 150, height: 96, borderRadius: 8, background: '#232b1e', transform: 'translate(14px,12px) rotate(4deg)' }} />
    <div style={{ position: 'absolute', width: 150, height: 96, borderRadius: 8, background: '#2e3627', transform: 'translate(7px,6px) rotate(2deg)' }} />
    <div style={{ position: 'relative', width: 156, height: 100, borderRadius: 8, background: '#fbfdf8', padding: '12px 14px', boxShadow: '0 10px 22px -10px rgba(0,0,0,.6)' }}>
      <div style={{ fontSize: 11.5, fontWeight: 800, color: '#1d2416', letterSpacing: '-.01em' }}>Self-Attention</div>
      <div style={{ width: 34, height: 3, background: '#7bd33f', borderRadius: 2, margin: '5px 0 8px' }} />
      {[86, 70, 78].map((w, i) => <div key={i} style={{ width: w, height: 4, background: '#dde5d3', borderRadius: 2, marginTop: 5 }} />)}
      <div style={{ position: 'absolute', bottom: 8, right: 12, fontFamily: mono, fontSize: 8, color: '#a9b59c' }}>12 / 18</div>
    </div>
  </div>
)

const ConceptCard = () => (
  <div style={{ ...cardBase, background: 'linear-gradient(150deg,#15240c,#0a1206)', border: '1px solid #2c4318', padding: '30px 18px 16px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
    <Badge>key idea</Badge>
    <div style={{ fontSize: 34, lineHeight: .8, color: '#7bd33f', fontFamily: 'Georgia,serif' }}>“</div>
    <div style={{ fontSize: 13.5, fontWeight: 650, color: '#e9f2df', lineHeight: 1.45, fontStyle: 'italic' }}>
      Attention is just a data-dependent weighted average.
    </div>
    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
      <span style={{ fontFamily: mono, fontSize: 9, background: '#1f6feb26', color: '#79c0ff', borderRadius: 4, padding: '2px 6px' }}>57:11</span>
      <span style={{ fontFamily: mono, fontSize: 9, color: '#66735b' }}>Karpathy · Let's build GPT</span>
    </div>
  </div>
)

const ARTIFACTS = [
  { key: 'notebook', C: NotebookCard }, { key: 'mindmap', C: MindmapCard },
  { key: 'dashboard', C: DashboardCard }, { key: 'flashcards', C: FlashcardCard },
  { key: 'chart', C: ChartCard }, { key: 'sheet', C: SheetCard },
  { key: 'slides', C: SlidesCard }, { key: 'concept', C: ConceptCard },
]

// creator studio — artifacts get remixed into decks, posts, threads
const RemixCard = () => (
  <div style={{ ...cardBase, background: '#101509', border: '1px solid #2c4318', padding: '26px 12px 10px' }}>
    <Badge>creator studio</Badge>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: '100%' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {[['▤', 'chart'], ['❝', 'quote'], ['⌗', 'code']].map(([g, t]) => (
          <div key={t} style={{ display: 'flex', gap: 5, alignItems: 'center', background: '#1a2213', border: '1px solid #2c3a24', borderRadius: 7, padding: '5px 8px' }}>
            <span style={{ color: '#8ee23e', fontSize: 11 }}>{g}</span>
            <span style={{ fontFamily: mono, fontSize: 8.5, color: '#b9c7ab' }}>{t}</span>
          </div>
        ))}
      </div>
      <div style={{ color: '#7bd33f', fontSize: 16 }}>→</div>
      <div style={{ flex: 1, alignSelf: 'stretch', display: 'flex', flexDirection: 'column', gap: 5, paddingBottom: 4 }}>
        <div style={{ flex: 1.5, background: '#fbfdf8', borderRadius: 7, padding: '7px 9px' }}>
          <div style={{ fontSize: 8.5, fontWeight: 800, color: '#1d2416' }}>Your next talk</div>
          <div style={{ width: 26, height: 2.5, background: '#7bd33f', borderRadius: 2, margin: '3px 0 5px' }} />
          <div style={{ display: 'flex', gap: 4 }}>
            <span style={{ flex: 1, height: 22, background: '#e4ebda', borderRadius: 4 }} />
            <span style={{ flex: 1, height: 22, background: '#cfe6b4', borderRadius: 4 }} />
          </div>
        </div>
        <div style={{ flex: 1, background: '#151b0e', border: '1px solid #2c3a24', borderRadius: 7, padding: '5px 9px' }}>
          <div style={{ fontFamily: mono, fontSize: 7.5, color: '#8ee23e' }}>@you · thread 🧵</div>
          <div style={{ width: '85%', height: 3.5, background: '#2c3a24', borderRadius: 2, marginTop: 4 }} />
          <div style={{ width: '60%', height: 3.5, background: '#2c3a24', borderRadius: 2, marginTop: 3 }} />
        </div>
      </div>
    </div>
  </div>
)

const SCENES = [
  { key: 'dashboard', C: DashboardCard, title: 'A dashboard you can touch', blurb: 'Every figure in the video becomes a live widget beside the player — drag the matrix, sweep the temperature, watch it recompute.' },
  { key: 'notebook', C: NotebookCard, title: 'Notebooks with the video\'s own code', blurb: 'The code on screen becomes runnable Python in your browser — sliders wired to the variables. Export to Jupyter for tonight\'s lab.' },
  { key: 'mindmap', C: MindmapCard, title: 'The lecture\'s concept graph', blurb: 'See how every idea hangs together — one glance instead of two hours of scrubbing.' },
  { key: 'flashcards', C: FlashcardCard, title: 'Flashcards that mint themselves', blurb: 'Key questions extracted per chapter, scheduled for spaced recall. Study the lecture, not your notes.' },
  { key: 'chart', C: ChartCard, title: 'Every plot, re-plotted live', blurb: 'Curves from the whiteboard become interactive charts — with the exact values the speaker used.' },
  { key: 'sheet', C: SheetCard, title: 'The speaker\'s numbers, editable', blurb: 'Financial and data examples land as sheets — swap in your own numbers and re-run the scenario.' },
  { key: 'slides', C: SlidesCard, title: 'A deck in one click', blurb: 'Selected moments become slides — each one linking back to its live widget for in-class play.' },
  { key: 'concept', C: ConceptCard, title: 'Key ideas, quotable', blurb: 'The claims that matter, timestamped and cited — ready for your notes or your newsletter.' },
  { key: 'remix', C: RemixCard, title: 'Creator studio: remix everything', blurb: 'Creators and educators reuse any artifact — charts into decks, quotes into threads, notebooks into courses. One lecture, endless content.' },
]

// a continuously flowing river of artifacts — never parks, slows on hover
function ArtifactCarousel({ T }) {
  const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const refs = useRef([])
  const wrapRef = useRef(null)
  const [centerIdx, setCenterIdx] = useState(0)
  const st = useRef({ t: 0, target: 0, hover: false, last: 0, center: 0 })
  const GAP = 252
  const TOTAL = SCENES.length * GAP
  useEffect(() => {
    if (reduced) return
    const s = st.current
    s.t = s.target = -TOTAL / 2 // scene 0 starts centered
    let raf
    const frame = (now) => {
      const dt = Math.min(.05, (now - (s.last || now)) / 1000)
      s.last = now
      if (!s.hover) s.target += 34 * dt // the river's pace
      s.t += (s.target - s.t) * Math.min(1, dt * 5)
      const stageW = wrapRef.current ? wrapRef.current.offsetWidth : 880
      SCENES.forEach((sc, i) => {
        const el = refs.current[i]
        if (!el) return
        const c = ((((i * GAP - s.t) % TOTAL) + TOTAL) % TOTAL) - TOTAL / 2
        const a = Math.abs(c)
        const scale = Math.max(.74, 2.05 - a * .0052)
        el.style.transform = `translateX(${c}px) translateY(${a * .1}px) rotateY(${Math.max(-30, Math.min(30, -c * .075))}deg) scale(${scale})`
        el.style.opacity = a > stageW / 2 + 80 ? 0 : String(Math.max(.15, 1 - a * .0028))
        el.style.zIndex = String(Math.max(1, 200 - Math.round(a)))
        if (a < GAP / 2 && s.center !== i) { s.center = i; setCenterIdx(i) }
      })
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [reduced])
  const S = SCENES[centerIdx]
  const arrow = {
    background: T.panel, border: `1px solid ${T.line}`, color: T.text, width: 44, height: 44,
    borderRadius: 999, fontSize: 18, cursor: 'pointer', flexShrink: 0, zIndex: 6,
  }
  return (
    <div style={{ padding: '54px 0 26px', textAlign: 'center' }}
      onMouseEnter={() => { st.current.hover = true }} onMouseLeave={() => { st.current.hover = false }}>
      <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>what comes out</div>
      <h2 style={{ fontSize: 'clamp(24px,3.4vw,34px)', color: T.text, letterSpacing: '-.02em', margin: '10px auto 0', maxWidth: '26ch', textWrap: 'balance' }}>
        Eight artifacts. One drop.
      </h2>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'clamp(6px,2vw,20px)', marginTop: 6 }}>
        <button aria-label="previous" onClick={() => { st.current.target -= GAP }} style={arrow}>‹</button>
        <div ref={wrapRef} style={{ position: 'relative', width: 'min(880px, 82vw)', height: 486, overflow: 'hidden', perspective: 1300 }}>
          {SCENES.map((Sc, i) => (
            <div key={Sc.key} ref={el => { refs.current[i] = el }}
              style={{ position: 'absolute', left: '50%', top: 112, marginLeft: -98,
                transformStyle: 'preserve-3d', willChange: 'transform, opacity',
                ...(reduced && i !== 0 ? { display: 'none' } : null),
                ...(reduced && i === 0 ? { transform: 'scale(2.05)' } : null) }}>
              <Sc.C />
            </div>
          ))}
          <AnimatePresence mode="wait">
            <motion.div key={S.key}
              initial={reduced ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8, transition: { duration: .18 } }}
              style={{ position: 'absolute', left: 0, right: 0, bottom: 0 }}>
              <div style={{ color: T.text, fontSize: 19, fontWeight: 750 }}>{S.title}</div>
              <div style={{ color: T.muted, fontSize: 13.5, lineHeight: 1.5, maxWidth: '48ch', margin: '5px auto 0' }}>{S.blurb}</div>
            </motion.div>
          </AnimatePresence>
        </div>
        <button aria-label="next" onClick={() => { st.current.target += GAP }} style={arrow}>›</button>
      </div>
    </div>
  )
}

// typewriter headline — types itself when scrolled into view, caret keeps blinking
function TypeTitle({ text, T }) {
  const ref = useRef(null)
  const [on, setOn] = useState(false)
  const [n, setN] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ob = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); ob.disconnect() } }, { rootMargin: '-40px' })
    ob.observe(el)
    return () => ob.disconnect()
  }, [])
  useEffect(() => {
    if (!on || n >= text.length) return
    const id = setTimeout(() => setN(x => x + 1), 55)
    return () => clearTimeout(id)
  }, [on, n, text])
  return (
    <h2 ref={ref} style={{ fontSize: 'clamp(24px,3.4vw,34px)', color: T.text, letterSpacing: '-.02em', margin: '10px auto 4px' }}>
      <span style={{ position: 'relative', display: 'inline-block' }}>
        <span style={{ visibility: 'hidden' }}>{text}</span>
        <span style={{ position: 'absolute', left: 0, top: 0, width: '100%', textAlign: 'left' }}>
          {text.slice(0, n)}
          <motion.span animate={{ opacity: [1, 0, 1] }} transition={{ duration: .9, repeat: Infinity }}
            style={{ display: 'inline-block', width: '.5ch', height: '.9em', background: T.acc, verticalAlign: '-0.08em', marginLeft: 3, borderRadius: 2 }} />
        </span>
      </span>
    </h2>
  )
}

// animated vector backdrops for the market tiles — one little world per persona
function MarketBG({ kind, color }) {
  const wrap = { position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 0 }
  if (kind === 'student') return ( // math drifting up from tonight's lab
    <div style={wrap} aria-hidden="true">
      {['∑', '∫', 'π', '∂', 'x²'].map((g, i) => (
        <motion.span key={i}
          animate={{ y: [16, -110], opacity: [0, .85, 0] }}
          transition={{ duration: 5.5 + i * 1.1, repeat: Infinity, delay: i * 1.2, ease: 'linear' }}
          style={{ position: 'absolute', bottom: -14, left: `${10 + i * 19}%`, fontFamily: mono,
            fontSize: 16 + (i % 3) * 7, fontWeight: 700, color: color + '30' }}>{g}</motion.span>
      ))}
    </div>
  )
  if (kind === 'teacher') return ( // a deck shuffling itself
    <div style={wrap} aria-hidden="true">
      {[0, 1, 2].map(i => (
        <motion.span key={i}
          animate={{ y: [0, -5, 0], opacity: [.5, 1, .5] }}
          transition={{ duration: 3.4, repeat: Infinity, delay: i * .55, ease: 'easeInOut' }}
          style={{ position: 'absolute', right: 12 + i * 12, bottom: 8 + i * 10, width: 62, height: 40,
            border: `1.5px solid ${color}38`, borderRadius: 6, background: color + '0d' }}>
          <span style={{ display: 'block', margin: '7px 8px 0', height: 3, borderRadius: 2, background: color + '45', width: 26 }} />
          <span style={{ display: 'block', margin: '4px 8px 0', height: 2, borderRadius: 2, background: color + '2b', width: 38 }} />
        </motion.span>
      ))}
    </div>
  )
  if (kind === 'creator') return ( // an equalizer that never stops
    <div style={wrap} aria-hidden="true">
      {[...Array(9)].map((_, i) => (
        <motion.span key={i}
          animate={{ scaleY: [.25, 1, .4, .85, .25] }}
          transition={{ duration: 2.1 + (i % 4) * .35, repeat: Infinity, delay: i * .13, ease: 'easeInOut' }}
          style={{ position: 'absolute', bottom: 0, left: `${7 + i * 10}%`, width: 5, height: 36,
            transformOrigin: 'bottom', background: color + '38', borderRadius: '3px 3px 0 0' }} />
      ))}
    </div>
  )
  return ( // researcher — a constellation of findings
    <svg viewBox="0 0 220 170" preserveAspectRatio="xMidYMid slice" aria-hidden="true" style={wrap}>
      {[[30, 128, 80, 62], [80, 62, 158, 98], [158, 98, 122, 146], [80, 62, 190, 34]].map(([x1, y1, x2, y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth="1" opacity=".14" />
      ))}
      {[[30, 128, 4], [80, 62, 5], [158, 98, 4], [122, 146, 3], [190, 34, 3.5]].map(([cx, cy, r], i) => (
        <motion.circle key={i} cx={cx} cy={cy} r={r} fill={color}
          animate={{ opacity: [.15, .55, .15] }}
          transition={{ duration: 2.6, repeat: Infinity, delay: i * .5, ease: 'easeInOut' }} />
      ))}
    </svg>
  )
}

const HOW_STEPS = [
  { n: '01', title: 'Drop a lecture', body: 'Paste any YouTube link — a 2-hour course or a 10-minute explainer. Any topic.', tag: 'you · 5 seconds' },
  { n: '02', title: 'The agent watches it', body: 'Nemotron Omni reads the frames and transcript — every figure, equation and code block, with the speaker\'s actual numbers.', tag: 'agent · vision + reasoning' },
  { n: '03', title: 'Artifacts appear', body: 'A touchable dashboard, runnable notebooks, flashcards, mind maps, charts, sheets and slides — minted from the video itself.', tag: 'agent · builds & verifies' },
  { n: '04', title: 'Learn, remix, repeat', body: 'Tweak and run everything. Export to Jupyter, decks or threads. The agent keeps watching for new uploads on a heartbeat.', tag: 'you + agent · forever' },
]

function HowItWorks({ T }) {
  return (
    <div style={{ maxWidth: 940, margin: '0 auto', padding: '54px 24px 10px' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>how it works</div>
        <h2 style={{ fontSize: 'clamp(24px,3.4vw,34px)', color: T.text, letterSpacing: '-.02em', margin: '10px auto 26px', maxWidth: '28ch', textWrap: 'balance' }}>
          From link to lab in one drop.
        </h2>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
        {HOW_STEPS.map((s, i) => (
          <motion.div key={s.n}
            initial={{ opacity: 0, y: 22 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ delay: i * 0.1, type: 'spring', stiffness: 160, damping: 20 }}
            className="edu-card"
            style={{ position: 'relative', background: T.panel, border: `1px solid ${T.line}`, borderRadius: 14, padding: '18px 16px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: mono, fontSize: 26, fontWeight: 800, color: T.acc, letterSpacing: '-.02em' }}>{s.n}</span>
              {i < HOW_STEPS.length - 1 && <span style={{ color: T.faint, fontSize: 16 }}>→</span>}
            </div>
            <div style={{ color: T.text, fontSize: 15.5, fontWeight: 750, marginTop: 8 }}>{s.title}</div>
            <div style={{ color: T.muted, fontSize: 12.5, lineHeight: 1.55, marginTop: 6 }}>{s.body}</div>
            <div style={{ fontFamily: mono, fontSize: 9.5, color: T.faint, marginTop: 12, letterSpacing: '.06em', textTransform: 'uppercase' }}>{s.tag}</div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

// the hero loop — a lecture pours into the funnel, an artifact comes out. Forever.
function HeroDrop({ T, onOpen }) {
  const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [cycle, setCycle] = useState(0)
  useEffect(() => {
    if (reduced) return
    const id = setInterval(() => setCycle(c => c + 1), 4400)
    return () => clearInterval(id)
  }, [reduced])
  const scene = SCENES[cycle % SCENES.length]
  const Art = scene.C
  // shelf of artifacts already minted this session (newest right)
  const made = []
  for (let k = Math.max(0, cycle - 6); k < cycle; k++) made.push({ s: SCENES[k % SCENES.length], k })
  return (
    <div style={{ position: 'relative', marginTop: 6 }}>
      <div style={{ position: 'relative', height: 545 }}>
        {/* funnel */}
        <svg width="640" height="250" viewBox="0 0 640 250" aria-hidden="true"
          style={{ position: 'absolute', top: 30, left: '50%', transform: 'translateX(-50%)', zIndex: 0, maxWidth: '96vw' }}>
          <path d="M20,6 L620,6 L365,150 L365,244 L275,244 L275,150 Z"
            fill={T.panel} stroke={T.line} strokeWidth="1.8" opacity=".9" />
          <path d="M20,6 L620,6" stroke={T.acc} strokeWidth="2.5" opacity=".55" />
          {/* mouth flash when the lecture lands */}
          {!reduced && (
            <motion.path key={`flash-${cycle}`} d="M20,6 L620,6" stroke={T.acc} strokeWidth="4"
              initial={{ opacity: 0 }} animate={{ opacity: [0, .95, 0] }}
              transition={{ delay: 1.35, duration: .55 }} />
          )}
        </svg>
        {/* the lecture card — arcs in, sinks into the throat */}
        <motion.button key={`vid-${cycle}`} onClick={() => onOpen('kCc8FmEb1nY')}
          initial={reduced ? false : { x: -340, y: -170, opacity: 0, rotate: -16 }}
          animate={reduced ? { opacity: 1 } : {
            x: [-340, -220, -95, -10, 0, 0],
            y: [-170, -150, -85, -14, 0, 92],
            rotate: [-16, -11, -5, 1, 0, 0],
            scale: [1, 1, 1, 1, .92, .26],
            opacity: [0, 1, 1, 1, 1, 0],
          }}
          transition={{ delay: .15, duration: 1.55, times: [0, .2, .42, .6, .7, 1], ease: 'easeIn' }}
          style={{ position: 'absolute', top: 0, left: '50%', marginLeft: -125, width: 250, zIndex: 2,
            background: T.panel, border: `1px solid ${T.line}`, borderRadius: 13, padding: 7, cursor: 'pointer',
            textAlign: 'left', overflow: 'hidden', boxShadow: '0 30px 60px -24px rgba(0,0,0,.6)' }}>
          <div style={{ position: 'relative' }}>
            <img src="https://i.ytimg.com/vi/kCc8FmEb1nY/mqdefault.jpg" alt=""
              style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', borderRadius: 8, display: 'block' }} />
            <span style={{ position: 'absolute', right: 5, bottom: 5, fontFamily: mono, fontSize: 9.5, background: '#000c', color: '#fff', borderRadius: 4, padding: '1px 5px' }}>1:56:20</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 3px 1px' }}>
            <span style={{ color: T.text, fontSize: 11.5, fontWeight: 700 }}>Karpathy — Let's build GPT</span>
            <span style={{ fontFamily: mono, fontSize: 9, color: T.acc }}>▶</span>
          </div>
        </motion.button>
        {/* distillate dripping from the stem */}
        {!reduced && [0, 1].map(i => (
          <motion.span key={i}
            animate={{ opacity: [0, 1, 0], y: [0, 34] }}
            transition={{ delay: 1.6 + i * .4, duration: .9, repeat: Infinity, repeatDelay: 1.2, ease: 'easeIn' }}
            style={{ position: 'absolute', top: 272, left: `calc(50% + ${(i - .5) * 14}px)`, width: 8, height: 8, borderRadius: 2, background: T.acc, zIndex: 0 }} />
        ))}
        {/* the artifact — the star. Pops out of the stem, holds, slides to the shelf */}
        <AnimatePresence>
          <motion.div key={`art-${cycle}`}
            initial={reduced ? false : { y: -36, scale: .2, opacity: 0 }}
            animate={{ y: 12, scale: 1.34, opacity: 1 }}
            exit={{ y: 130, scale: .42, opacity: 0, transition: { duration: .45, ease: 'easeIn' } }}
            transition={{ delay: reduced ? 0 : 1.7, type: 'spring', stiffness: 130, damping: 16 }}
            style={{ position: 'absolute', top: 292, left: '50%', marginLeft: -98, zIndex: 3, transformOrigin: '50% 0%' }}>
            <Art />
          </motion.div>
        </AnimatePresence>
        {/* caption for the artifact on stage */}
        <motion.div key={`cap-${cycle}`}
          initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: reduced ? 0 : 2.1 }}
          style={{ position: 'absolute', top: 522, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontSize: 11.5, color: T.acc, zIndex: 3 }}>
          {scene.title}
        </motion.div>
      </div>
      {/* the shelf — everything minted so far */}
      <div style={{ height: 96, marginTop: 16, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: 8 }}>
        {made.map(({ s, k }) => (
          <motion.div key={k} initial={{ scale: .5, opacity: 0, y: -16 }} animate={{ scale: 1, opacity: .9, y: 0 }}
            transition={{ type: 'spring', stiffness: 180, damping: 20 }}
            style={{ width: 86, height: 71, overflow: 'hidden', borderRadius: 8, border: `1px solid ${T.line}`, flexShrink: 0 }}>
            <div style={{ transform: 'scale(.439)', transformOrigin: 'top left' }}><s.C /></div>
          </motion.div>
        ))}
        {made.length > 0 && (
          <div style={{ alignSelf: 'center', fontFamily: mono, fontSize: 10, color: T.faint, marginLeft: 6 }}>
            {cycle >= SCENES.length ? '∞ on a heartbeat' : `+${SCENES.length - cycle} more…`}
          </div>
        )}
      </div>
    </div>
  )
}

// centered video coverflow — one shelf per genre, in flow
function VideoCarousel({ T, onOpen, vids }) {
  const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [idx, setIdx] = useState(0)
  const [paused, setPaused] = useState(false)
  const many = vids.length > 1
  const go = (n) => setIdx((n + vids.length) % vids.length)
  useEffect(() => {
    if (reduced || paused || !many) return
    const id = setInterval(() => go(idx + 1), 4200)
    return () => clearInterval(id)
  }, [idx, paused, reduced, many])
  const arrow = { background: T.panel, border: `1px solid ${T.line}`, color: T.text, width: 44, height: 44, borderRadius: 999, fontSize: 18, cursor: 'pointer', flexShrink: 0, zIndex: 6, visibility: many ? 'visible' : 'hidden' }
  // 3+ videos: full coverflow; 2: center + right wing; 1: lone centered card
  const offs = vids.length >= 3 ? [-1, 0, 1] : vids.length === 2 ? [0, 1] : [0]
  return (
    <div style={{ textAlign: 'center' }} onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'clamp(6px,2vw,20px)' }}>
        <button aria-label="previous" onClick={() => go(idx - 1)} style={arrow}>‹</button>
        <div style={{ position: 'relative', width: 'min(900px, 84vw)', height: 400, overflow: 'hidden', perspective: 1300 }}>
          {offs.map(off => {
            const i = (idx + off + vids.length) % vids.length
            const v = vids[i]
            const center = off === 0
            const xo = typeof window !== 'undefined' ? Math.min(300, window.innerWidth * 0.28) : 300
            const xShift = vids.length === 2 ? -xo / 2 : 0 // balance the pair around the middle
            return (
              <motion.div key={v.id}
                animate={{ x: off * xo + xShift, rotateY: off * -24, scale: center ? 1.08 : .8, opacity: center ? 1 : .38, zIndex: center ? 5 : 1 }}
                transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 150, damping: 22 }}
                onClick={() => center ? onOpen(v.id) : go(idx + off)}
                style={{ position: 'absolute', left: '50%', top: 16, marginLeft: -170, width: 340, cursor: 'pointer', transformStyle: 'preserve-3d' }}>
                <div style={{ background: T.panel, border: `1px solid ${center ? T.acc + '66' : T.line}`, borderRadius: 16, overflow: 'hidden', textAlign: 'left', boxShadow: center ? '0 30px 70px -28px rgba(0,0,0,.6)' : 'none' }}>
                  <img src={`https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`} alt=""
                    style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }} />
                  <div style={{ padding: '10px 12px 12px' }}>
                    <div style={{ fontSize: 13, color: T.text, fontWeight: 650, lineHeight: 1.35, minHeight: 35 }}>{v.title}</div>
                    <div style={{ display: 'flex', gap: 2, height: 5, borderRadius: 3, overflow: 'hidden', marginTop: 8 }}>
                      {v.inside.mix.map(([c, n], j) => <span key={j} style={{ flex: n, background: c, borderRadius: 2 }} />)}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 7 }}>
                      <span style={{ fontFamily: mono, fontSize: 10, color: T.acc }}>{v.inside.count}</span>
                      <span style={{ fontFamily: mono, fontSize: 10, color: T.faint }}>{center ? 'open →' : ''}</span>
                    </div>
                    {center && (
                      <div style={{ marginTop: 8, borderTop: `1px solid ${T.line}`, paddingTop: 7 }}>
                        {v.inside.peek.map(([t, label, c]) => (
                          <div key={t} style={{ display: 'flex', gap: 7, alignItems: 'center', marginTop: 3 }}>
                            <span style={{ fontFamily: mono, fontSize: 9, color: '#79c0ff', background: '#1f6feb22', borderRadius: 3, padding: '1px 4px', flexShrink: 0 }}>{t}</span>
                            <span style={{ width: 6, height: 6, borderRadius: 3, background: c, flexShrink: 0 }} />
                            <span style={{ fontSize: 11, color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
        <button aria-label="next" onClick={() => go(idx + 1)} style={arrow}>›</button>
      </div>
      {many && (
        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginTop: 4 }}>
          {vids.map((v, i) => (
            <button key={v.id} aria-label={v.title} onClick={() => go(i)}
              style={{ width: i === idx ? 20 : 7, height: 7, borderRadius: 4, border: 'none', cursor: 'pointer', background: i === idx ? T.acc : T.line, transition: 'all .25s', padding: 0 }} />
          ))}
        </div>
      )}
    </div>
  )
}

function Landing({ onOpen }) {
  const [url, setUrl] = useState('')
  const [err, setErr] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('8kedu-theme') || 'dark')
  const T = THEMES[theme]
  useEffect(() => {
    localStorage.setItem('8kedu-theme', theme)
    document.documentElement.style.background = T.solid
  }, [theme, T.solid])
  const [live, setLive] = useState(null)
  useEffect(() => {
    fetch('/agent/library').then(r => r.json()).then(d => { if (d.ok) setLive(d.videos) }).catch(() => {})
  }, [])
  const gallery = useMemo(() => mergeGallery(live), [live])
  const go = () => {
    const id = parseVideoId(url.trim())
    if (!id) { setErr('paste a YouTube link (or 11-char video id)'); return }
    onOpen(id)
  }
  const rise = { hide: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 120, damping: 18 } } }
  return (
    <div style={{ minHeight: '100vh', background: T.bg }}>
      <LandingStyles acc={T.acc} />
      {/* top bar */}
      <div style={{ position: 'relative', zIndex: 2, maxWidth: 1040, margin: '0 auto', padding: '18px 24px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Logo size={30} wordColor={T.text} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <a href="?view=learn" style={{ textDecoration: 'none', color: T.text, background: T.panel, border: `1px solid ${T.line}`, borderRadius: 999, padding: '7px 13px', fontSize: 13 }}>learn</a>
        <a href="?view=community" style={{ textDecoration: 'none', color: T.text, background: T.panel, border: `1px solid ${T.line}`, borderRadius: 999, padding: '7px 13px', fontSize: 13 }}>community</a>
        <a href="?view=agent"
          style={{ display: 'flex', alignItems: 'center', gap: 7, textDecoration: 'none', background: T.panel, border: `1px solid ${T.acc}55`, color: T.text, borderRadius: 999, padding: '7px 13px', fontSize: 13, cursor: 'pointer' }}>
          <span className="edu-pulse" style={{ width: 8, height: 8, borderRadius: 4, background: T.acc, display: 'inline-block' }} />
          agent live
        </a>
        <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="toggle theme"
          style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>
          {theme === 'dark' ? '☀ light' : '☾ dark'}
        </button>
        </div>
      </div>
      {/* HERO */}
      <div style={{ position: 'relative', overflow: 'hidden', borderBottom: `1px solid ${T.line}` }}>
        <AttentionField light={T.field} />
        <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(760px 360px at 50% 44%, transparent, ${T.solid}dd 80%)` }} />
        <motion.div style={{ position: 'relative', maxWidth: 940, margin: '0 auto', padding: '52px 24px 68px', textAlign: 'center' }}
          initial="hide" animate="show" variants={{ show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } } }}>
          <motion.div variants={rise} style={{ fontFamily: 'ui-monospace,monospace', fontSize: 12, letterSpacing: '.24em', textTransform: 'uppercase', color: T.acc }}>
            <span className="edu-pulse">●</span>&nbsp; the resolution of understanding
          </motion.div>
          <motion.h1 variants={rise} style={{ fontSize: 'clamp(28px,4.4vw,46px)', lineHeight: 1.06, letterSpacing: '-.03em', margin: '12px auto 0', textWrap: 'balance', color: T.text, maxWidth: '26ch' }}>
            1 lecture, 8 ways to learn it. Understand <span style={{ color: T.acc }}>8× faster</span>.
          </motion.h1>
          <motion.p variants={rise} style={{ fontSize: 'clamp(14px,1.9vw,17px)', color: T.sub, margin: '10px auto 0', fontWeight: 600 }}>
            An autonomous agent watches any lecture — and makes it touchable.
          </motion.p>
          <motion.div variants={rise}><HeroDrop T={T} onOpen={onOpen} /></motion.div>
          <motion.div variants={rise} style={{ display: 'flex', gap: 10, maxWidth: 540, margin: '18px auto 0', position: 'relative', zIndex: 2 }}>
            <input className="edu-in" value={url} onChange={e => { setUrl(e.target.value); setErr(null) }}
              onKeyDown={e => e.key === 'Enter' && go()} placeholder="drop a video to learn…"
              style={{ flex: 1, background: T.panel, color: T.text, border: `1px solid ${T.line}`, borderRadius: 12, padding: '15px 16px', fontSize: 15 }} />
            <motion.button className="edu-open" onClick={go} whileTap={{ scale: 0.96 }}
              style={{ background: T.acc, color: T.accText, border: 'none', borderRadius: 12, padding: '15px 28px', fontSize: 15, fontWeight: 800, cursor: 'pointer', whiteSpace: 'nowrap' }}>
              learn →
            </motion.button>
          </motion.div>
          {err && <div style={{ color: '#e5484d', fontSize: 13, marginTop: 10 }}>{err}</div>}
        </motion.div>
      </div>

      {/* LOOK CLOSER — full-size artifact carousel */}
      <ArtifactCarousel T={T} />

      {/* WHO IT'S FOR — markets */}
      <div style={{ maxWidth: 940, margin: '0 auto', padding: '30px 24px 0' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>who it's for</div>
          <TypeTitle text="Four markets. One engine." T={T} />
          <div style={{ color: T.muted, fontSize: 13.5 }}>every video analyzed once is cached for all — marginal cost per learner → 0</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginTop: 18 }}>
          {[
            ['student', '🎓', 'Students', '$400B', 'e-learning', '1.5B learners', 'tonight\'s lab, from tonight\'s lecture', .92, '#79c0ff'],
            ['teacher', '👩‍🏫', 'Teachers', '$160B', 'edtech tools', '85M educators', 'one-click decks, live in class', .55, '#ffab70'],
            ['creator', '✍️', 'Creators', '$250B', 'creator economy', '200M creators', 'one lecture → endless content', .72, '#ff9bce'],
            ['researcher', '🔬', 'Researchers', '$35B', 'research tools', '10M researchers', 'mint the widget you need', .3, '#b48eff'],
          ].map(([key, icon, title, big, label, pop, hook, arc, c], i) => (
            <motion.button key={key} onClick={() => onOpen('kCc8FmEb1nY', key)}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * .08, type: 'spring', stiffness: 170, damping: 20 }}
              className="edu-card" whileHover={{ borderColor: c + '77' }}
              style={{ textAlign: 'left', background: T.panel, border: `1px solid ${T.line}`, borderRadius: 14,
                padding: '16px 16px 14px', cursor: 'pointer', position: 'relative', overflow: 'hidden' }}>
              <MarketBG kind={key} color={c} />
              {/* market-share arc glyph */}
              <svg width="46" height="46" viewBox="0 0 46 46" style={{ position: 'absolute', top: 14, right: 12, opacity: .9, zIndex: 1 }}>
                <circle cx="23" cy="23" r="18" fill="none" stroke={T.line} strokeWidth="5" />
                <motion.circle cx="23" cy="23" r="18" fill="none" stroke={c} strokeWidth="5" strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 18}
                  initial={{ strokeDashoffset: 2 * Math.PI * 18 }}
                  whileInView={{ strokeDashoffset: 2 * Math.PI * 18 * (1 - arc) }}
                  viewport={{ once: true }} transition={{ delay: .3 + i * .1, duration: .9, ease: 'easeOut' }}
                  transform="rotate(-90 23 23)" />
              </svg>
              <span style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: T.muted }}>{icon} {title}</span>
                <span style={{ fontFamily: mono, fontSize: 'clamp(30px,3.4vw,38px)', fontWeight: 800, color: c, letterSpacing: '-.03em', lineHeight: 1.1, marginTop: 6 }}>{big}</span>
                <span style={{ fontFamily: mono, fontSize: 11, color: T.faint, textTransform: 'uppercase', letterSpacing: '.08em' }}>{label}</span>
                <span style={{ fontSize: 12.5, color: T.text, fontWeight: 650, marginTop: 10 }}>{pop}</span>
                <span style={{ fontSize: 11.5, color: T.muted }}>{hook}</span>
              </span>
            </motion.button>
          ))}
        </div>
      </div>

      {/* HOW IT WORKS */}
      <HowItWorks T={T} />

      {/* BODY */}
      <div style={{ maxWidth: 940, margin: '0 auto', padding: '44px 24px 80px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontFamily: 'ui-monospace,monospace', color: T.faint, fontSize: 12, textTransform: 'uppercase', letterSpacing: '.14em', textAlign: 'center' }}>
            ready to touch — any topic, not just code
          </div>
          {gallery.map((cat, ci) => (
            <motion.div key={cat.name}
              initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ type: 'spring', stiffness: 120, damping: 20, delay: ci * .06 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 8, marginBottom: 2 }}>
                <span style={{ fontSize: 15, fontWeight: 700, color: T.text }}>{cat.icon} {cat.name}</span>
                <span style={{ fontSize: 11.5, color: T.faint }}>{cat.videos.length} lecture{cat.videos.length > 1 ? 's' : ''}</span>
              </div>
              <VideoCarousel T={T} onOpen={onOpen} vids={cat.videos.map(v => ({ ...v, tag: cat.name }))} />
            </motion.div>
          ))}
        </div>

        <div style={{ color: T.faint, fontSize: 12, fontFamily: 'ui-monospace,monospace' }}>
          yt-dlp → keyframes → Nemotron Omni → spec JSON → live widgets · python in-browser via pyodide · remix = a URL
        </div>
      </div>
    </div>
  )
}

// ————— R2: Community — the remix network —————
const WIDGET_TINT = { softmax: '#ff9bce', attention: '#ffab70', matrix_mul: '#79c0ff', function_plot: '#56d364', notebook: '#b48eff', composite: '#79c0ff', none: '#8b9682' }

function CommunityView({ onExit, onOpen }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('8kedu-theme') || 'dark')
  const T = THEMES[theme]
  useEffect(() => { localStorage.setItem('8kedu-theme', theme); document.documentElement.style.background = T.solid }, [theme, T.solid])
  const [sort, setSort] = useState('hot')
  const [items, setItems] = useState([])
  const [err, setErr] = useState(null)
  const load = async (s) => {
    try {
      const r = await fetch(`/pub/feed?sort=${s ?? sort}`); const d = await r.json()
      if (d.ok) { setItems(d.items); setErr(null) } else setErr(d.error)
    } catch (e) { setErr('agent api offline — start agent/api.py') }
  }
  useEffect(() => { load() }, [sort])
  const upvote = async (id) => {
    try { const r = await fetch('/pub/vote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ artifact_id: id, voter: `me-${Math.floor(Date.now() / 1)}` }) }); const d = await r.json(); if (d.ok) setItems(x => x.map(a => a.id === id ? { ...a, votes: d.votes } : a)) } catch (e) {}
  }
  const remix = async (id) => {
    try { await fetch('/pub/fork', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ artifact_id: id }) }); load() } catch (e) {}
  }
  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
      <LandingStyles acc={T.acc} />
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '18px 24px 70px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button onClick={onExit} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>← site</button>
            <Logo size={28} wordColor={T.text} />
          </div>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>{theme === 'dark' ? '☀' : '☾'}</button>
        </div>

        <div style={{ marginTop: 26, textAlign: 'center' }}>
          <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>the remix network</div>
          <h1 style={{ fontSize: 'clamp(26px,4vw,42px)', letterSpacing: '-.03em', margin: '8px 0 0', textWrap: 'balance' }}>Every artifact is a remix waiting to happen.</h1>
          <p style={{ color: T.sub, fontSize: 15, marginTop: 8 }}>learners publish what the agent made · upvote the best · fork any of it into your own</p>
          <div style={{ display: 'inline-flex', gap: 4, marginTop: 16, background: T.panel, border: `1px solid ${T.line}`, borderRadius: 999, padding: 4 }}>
            {['hot', 'new'].map(s => (
              <button key={s} onClick={() => setSort(s)} style={{ background: sort === s ? T.acc : 'transparent', color: sort === s ? T.accText : T.muted, border: 'none', borderRadius: 999, padding: '6px 18px', fontSize: 13, fontWeight: 700, cursor: 'pointer', textTransform: 'capitalize' }}>{s === 'hot' ? '🔥 hot' : '🆕 new'}</button>
            ))}
          </div>
        </div>

        {err && <div style={{ color: '#e5484d', fontSize: 13, marginTop: 16, textAlign: 'center' }}>{err}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 14, marginTop: 26 }}>
          {items.map((a, i) => {
            const tint = WIDGET_TINT[a.widget] || T.acc
            return (
              <motion.div key={a.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * .04, .4) }}
                className="edu-card" style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                {/* thumbnail band tinted by widget type */}
                <div style={{ position: 'relative', height: 96, background: `linear-gradient(135deg, ${tint}22, ${tint}05)`, borderBottom: `1px solid ${T.line}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <img src={`https://i.ytimg.com/vi/${a.video_id}/mqdefault.jpg`} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: .28 }} />
                  <span style={{ position: 'relative', fontFamily: mono, fontSize: 11, fontWeight: 700, color: tint, background: '#0009', border: `1px solid ${tint}55`, borderRadius: 6, padding: '4px 10px', textTransform: 'uppercase', letterSpacing: '.06em' }}>{a.widget}</span>
                  {a.remixed_from && <span style={{ position: 'absolute', top: 8, right: 8, fontFamily: mono, fontSize: 9, color: T.text, background: '#0009', borderRadius: 5, padding: '2px 7px' }}>⑃ remix</span>}
                </div>
                <div style={{ padding: '12px 13px 13px', display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 650, color: T.text, lineHeight: 1.35, minHeight: 36 }}>{a.title}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: mono, fontSize: 11, color: T.faint }}>
                    <span style={{ width: 18, height: 18, borderRadius: 9, background: tint, color: '#0a0d08', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 800 }}>{a.owner[0].toUpperCase()}</span>
                    by {a.owner}
                  </div>
                  <div style={{ display: 'flex', gap: 6, marginTop: 'auto' }}>
                    <button onClick={() => upvote(a.id)} style={{ display: 'flex', alignItems: 'center', gap: 5, background: T.bg, border: `1px solid ${T.line}`, color: T.text, borderRadius: 8, padding: '7px 11px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>▲ {a.votes}</button>
                    <button onClick={() => remix(a.id)} style={{ flex: 1, background: T.bg, border: `1px solid ${T.line}`, color: T.text, borderRadius: 8, padding: '7px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>⑃ remix</button>
                    <button onClick={() => onOpen(a.video_id)} style={{ background: tint, border: 'none', color: '#0a0d08', borderRadius: 8, padding: '7px 12px', fontSize: 12.5, fontWeight: 800, cursor: 'pointer' }}>open</button>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
        {!items.length && !err && <div style={{ color: T.faint, textAlign: 'center', marginTop: 40 }}>no public artifacts yet</div>}
        <div style={{ textAlign: 'center', marginTop: 26, fontFamily: mono, fontSize: 12, color: T.faint }}>
          a remix is just a URL · publish is one tap · <span style={{ color: T.muted }}>identity + profiles land with Supabase Auth (next)</span>
        </div>
      </div>
    </div>
  )
}

// ————— R1: Learn — dynamic curriculum, Duolingo-style —————
function LearnView({ onExit, onOpen }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('8kedu-theme') || 'dark')
  const T = THEMES[theme]
  useEffect(() => { localStorage.setItem('8kedu-theme', theme); document.documentElement.style.background = T.solid }, [theme, T.solid])
  const [stage, setStage] = useState('intake')      // intake → paths → course
  const [subject, setSubject] = useState('')
  const [kind, setKind] = useState('subject')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [proposal, setProposal] = useState(null)    // {goal_id, paths, titles}
  const [course, setCourse] = useState(null)        // {units}

  const SUGGEST = ['Reinforcement Learning', 'Deep Learning', 'How to buy my first house', 'How to make sourdough']

  const propose = async (subj) => {
    const s = (subj ?? subject).trim()
    if (!s) { setErr('type a subject'); return }
    setSubject(s); setBusy(true); setErr(null)
    try {
      const r = await fetch('/agent/learn/propose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subject: s, kind }) })
      const d = await r.json()
      if (!d.ok) { setErr(d.error || 'propose failed'); setBusy(false); return }
      setProposal(d); setStage('paths')
    } catch (e) { setErr('agent api offline — start agent/api.py') }
    setBusy(false)
  }
  const choose = async (path_id) => {
    setBusy(true)
    try {
      const r = await fetch('/agent/learn/choose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal_id: proposal.goal_id, path_id, titles: proposal.titles }) })
      const d = await r.json()
      if (!d.ok) { setErr(d.error || 'choose failed'); setBusy(false); return }
      setCourse(d); setStage('course')
    } catch (e) { setErr('choose failed') }
    setBusy(false)
  }

  const topbar = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={onExit} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>← site</button>
        <Logo size={28} wordColor={T.text} />
      </div>
      <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>{theme === 'dark' ? '☀' : '☾'}</button>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
      <LandingStyles acc={T.acc} />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '18px 24px 70px' }}>
        {topbar}

        {stage === 'intake' && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ marginTop: 64, textAlign: 'center' }}>
            <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>learn anything</div>
            <h1 style={{ fontSize: 'clamp(30px,5vw,52px)', letterSpacing: '-.03em', margin: '12px auto 0', textWrap: 'balance', maxWidth: '18ch' }}>What do you want to learn?</h1>
            <p style={{ color: T.sub, fontSize: 16, marginTop: 10 }}>the agent finds the videos, sequences a course, makes every step touchable.</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 20, flexWrap: 'wrap' }}>
              {[['subject', 'a subject'], ['concept', 'a concept'], ['how-to', 'a how-to']].map(([k, lbl]) => (
                <button key={k} onClick={() => setKind(k)} style={{ background: kind === k ? T.acc : T.panel, color: kind === k ? T.accText : T.text, border: `1px solid ${kind === k ? T.acc : T.line}`, borderRadius: 999, padding: '7px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>{lbl}</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, maxWidth: 560, margin: '16px auto 0' }}>
              <input className="edu-in" value={subject} onChange={e => { setSubject(e.target.value); setErr(null) }} onKeyDown={e => e.key === 'Enter' && propose()}
                placeholder="e.g. Reinforcement Learning" autoFocus
                style={{ flex: 1, background: T.panel, color: T.text, border: `1px solid ${T.line}`, borderRadius: 12, padding: '15px 16px', fontSize: 15 }} />
              <motion.button onClick={() => propose()} whileTap={{ scale: .96 }} disabled={busy}
                style={{ background: T.acc, color: T.accText, border: 'none', borderRadius: 12, padding: '15px 26px', fontSize: 15, fontWeight: 800, cursor: busy ? 'wait' : 'pointer', whiteSpace: 'nowrap', opacity: busy ? .6 : 1 }}>
                {busy ? 'finding…' : 'build my course →'}
              </motion.button>
            </div>
            {err && <div style={{ color: '#e5484d', fontSize: 13, marginTop: 10 }}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 22, flexWrap: 'wrap' }}>
              {SUGGEST.map(s => (
                <button key={s} onClick={() => propose(s)} style={{ background: 'transparent', color: T.muted, border: `1px dashed ${T.line}`, borderRadius: 999, padding: '6px 14px', fontSize: 12.5, cursor: 'pointer' }}>{s}</button>
              ))}
            </div>
          </motion.div>
        )}

        {stage === 'paths' && proposal && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ marginTop: 40 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>the agent found {proposal.paths.reduce((m, p) => Math.max(m, p.video_ids.length), 0)} videos · pick a path</div>
              <h1 style={{ fontSize: 'clamp(24px,3.6vw,36px)', letterSpacing: '-.03em', margin: '10px 0 0', textWrap: 'balance' }}>Your course for “{proposal.subject}”</h1>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 14, marginTop: 24 }}>
              {proposal.paths.map((p, i) => (
                <motion.div key={p.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .1 }}
                  className="edu-card" style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: 18, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 18, fontWeight: 750 }}>{p.label}</span>
                    <span style={{ fontFamily: mono, fontSize: 11, color: T.faint }}>{p.video_ids.length} videos · ~{Math.round(p.est_minutes / 60 * 10) / 10}h</span>
                  </div>
                  <div style={{ color: T.muted, fontSize: 13, marginTop: 6, lineHeight: 1.5 }}>{p.rationale}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
                    {p.videos.map((v, j) => (
                      <div key={v.id} style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
                        <span style={{ fontFamily: mono, fontSize: 10, color: T.faint, width: 16 }}>{String(j + 1).padStart(2, '0')}</span>
                        <img src={`https://i.ytimg.com/vi/${v.id}/default.jpg`} alt="" style={{ width: 44, height: 26, objectFit: 'cover', borderRadius: 4, flexShrink: 0 }} />
                        <span style={{ fontSize: 12, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.title}</span>
                      </div>
                    ))}
                  </div>
                  <motion.button onClick={() => choose(p.id)} whileTap={{ scale: .97 }} disabled={busy}
                    style={{ marginTop: 16, background: T.acc, color: T.accText, border: 'none', borderRadius: 10, padding: '12px', fontSize: 14, fontWeight: 800, cursor: busy ? 'wait' : 'pointer', opacity: busy ? .6 : 1 }}>
                    start this path →
                  </motion.button>
                </motion.div>
              ))}
            </div>
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <button onClick={() => setStage('intake')} style={{ background: 'none', border: 'none', color: T.muted, fontSize: 13, cursor: 'pointer', textDecoration: 'underline' }}>← different subject</button>
            </div>
          </motion.div>
        )}

        {stage === 'course' && course && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ marginTop: 40 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>your course · {course.units.length} units</div>
              <h1 style={{ fontSize: 'clamp(24px,3.6vw,36px)', letterSpacing: '-.03em', margin: '10px 0 4px', textWrap: 'balance' }}>“{proposal.subject}” — built for you</h1>
              <p style={{ color: T.muted, fontSize: 13.5 }}>the agent processes each unit into touchable widgets · complete one to unlock the next</p>
            </div>
            {/* Duolingo-style unit spine */}
            <div style={{ maxWidth: 560, margin: '30px auto 0', position: 'relative' }}>
              {course.units.map((u, i) => {
                const unlocked = i === 0 || course.units[i - 1]?.widgets > 0
                const ready = u.widgets > 0
                return (
                  <motion.div key={u.video_id} initial={{ opacity: 0, x: i % 2 ? 30 : -30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * .12, type: 'spring', stiffness: 140, damping: 18 }}
                    style={{ display: 'flex', justifyContent: i % 2 ? 'flex-end' : 'flex-start', marginBottom: 14 }}>
                    <button onClick={() => ready && onOpen(u.video_id)} disabled={!ready}
                      style={{ display: 'flex', gap: 12, alignItems: 'center', width: 'min(420px,86%)', textAlign: 'left',
                        background: T.panel, border: `1px solid ${ready ? T.acc + '66' : T.line}`, borderRadius: 16, padding: 12,
                        cursor: ready ? 'pointer' : 'default', opacity: unlocked ? 1 : .5 }}>
                      <span style={{ width: 42, height: 42, borderRadius: 999, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 18, fontWeight: 800, background: ready ? T.acc : T.line, color: ready ? T.accText : T.faint }}>
                        {ready ? '▶' : (unlocked ? i + 1 : '🔒')}
                      </span>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13.5, fontWeight: 650, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.title}</div>
                        <div style={{ fontFamily: mono, fontSize: 10.5, color: ready ? '#56d364' : T.faint, marginTop: 2 }}>
                          {ready ? `✓ ${u.widgets} widgets ready — tap to learn` : (unlocked ? 'agent will process this next' : 'locked')}
                        </div>
                      </div>
                    </button>
                  </motion.div>
                )
              })}
            </div>
            <div style={{ textAlign: 'center', marginTop: 20, fontFamily: mono, fontSize: 12, color: T.faint }}>
              processing runs on the agent's heartbeat · <a href="?view=agent" style={{ color: T.acc }}>watch it live →</a>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

// ————— P3: the agent, live — judges SEE the autonomy —————
const ACTION_STYLE = {
  FIND_VIDEO: { c: '#79c0ff', label: 'find', glyph: '🔎' },
  PROCESS_VIDEO: { c: '#56d364', label: 'process', glyph: '⚙' },
  SEQUENCE: { c: '#b48eff', label: 'sequence', glyph: '✓' },
  MONITOR: { c: '#ffab70', label: 'monitor', glyph: '📡' },
  CURATE: { c: '#8ee23e', label: 'curate', glyph: '📚' },
  IDLE: { c: '#8b9682', label: 'idle', glyph: '·' },
}
const GENRE_LABEL = { ai_stem: 'AI & STEM', how_to: 'How-To', cooking: 'Cooking', finance: 'Finance', real_estate: 'Real estate', fitness: 'Fitness', unknown: 'Uncategorized' }
const tclock = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) } catch { return '' } }

function StatTile({ T, label, value, sub, accent }) {
  return (
    <div style={{ flex: 1, minWidth: 150, background: T.panel, border: `1px solid ${T.line}`, borderRadius: 14, padding: '14px 16px' }}>
      <div style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: '.1em', textTransform: 'uppercase', color: T.faint }}>{label}</div>
      <div style={{ fontFamily: mono, fontSize: 30, fontWeight: 800, letterSpacing: '-.03em', color: accent || T.acc, lineHeight: 1.15, marginTop: 4 }}>{value}</div>
      <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{sub}</div>
    </div>
  )
}

function AgentDashboard({ onExit }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('8kedu-theme') || 'dark')
  const T = THEMES[theme]
  const [state, setState] = useState(null)
  const [contain, setContain] = useState(null)
  const [ticking, setTicking] = useState(false)
  const [err, setErr] = useState(null)
  useEffect(() => { localStorage.setItem('8kedu-theme', theme); document.documentElement.style.background = T.solid }, [theme, T.solid])

  const load = async () => {
    try {
      const r = await fetch('/agent/state'); const d = await r.json()
      if (d.ok) { setState(d); setErr(null) } else setErr(d.error || 'agent api down')
    } catch (e) { setErr('agent api offline — start agent/api.py') }
  }
  useEffect(() => {
    load(); fetch('/agent/containment').then(r => r.json()).then(setContain).catch(() => {})
    const id = setInterval(load, 2500)
    return () => clearInterval(id)
  }, [])

  const wake = async () => {
    setTicking(true)
    try { await fetch('/agent/tick', { method: 'POST' }); await load() }
    catch (e) { setErr('tick failed') } finally { setTicking(false) }
  }

  const runs = state?.runs || []
  const curriculum = state?.curriculum || []
  const channels = state?.channels || []
  const library = state?.library || []
  const cache = state?.cache || { concepts_cached: 0, videos_cached: 0, reuses: 0, widgets_served_free: 0 }

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
      <LandingStyles acc={T.acc} />
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '18px 24px 60px' }}>
        {/* top bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button onClick={onExit} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>← site</button>
            <Logo size={28} wordColor={T.text} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: mono, fontSize: 12, color: T.muted }}>
              <motion.span animate={{ scale: [1, 1.5, 1], opacity: [1, .5, 1] }} transition={{ duration: 1.8, repeat: Infinity }}
                style={{ width: 9, height: 9, borderRadius: 5, background: err ? '#e5484d' : T.acc, display: 'inline-block' }} />
              {err ? 'offline' : 'heartbeat live'}
            </span>
            <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>
              {theme === 'dark' ? '☀' : '☾'}
            </button>
          </div>
        </div>

        {/* header */}
        <div style={{ marginTop: 26 }}>
          <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>the agent, live</div>
          <h1 style={{ fontSize: 'clamp(26px,4vw,40px)', letterSpacing: '-.03em', margin: '8px 0 0', textWrap: 'balance' }}>
            8kEdu is working — on a heartbeat, on its own.
          </h1>
          <div style={{ color: T.sub, fontSize: 15, marginTop: 6 }}>
            goal: <span style={{ color: T.text, fontWeight: 650 }}>{state?.goal || '…'}</span>
          </div>
        </div>

        {/* stat tiles */}
        <div style={{ display: 'flex', gap: 12, marginTop: 20, flexWrap: 'wrap' }}>
          <StatTile T={T} label="cache moat" value={cache.concepts_cached} sub={`widgets cached · ${cache.videos_cached} video${cache.videos_cached === 1 ? '' : 's'} · reused by every learner`} />
          <StatTile T={T} label="cache hit-rate" value={cache.infer_entries ? `${Math.round(cache.hit_rate * 100)}%` : '—'}
            sub={cache.infer_entries ? `${cache.infer_hits} of ${cache.infer_hits + cache.infer_entries} asks served without a model call` : 'frame-level ask cache'} accent="#56d364" />
          <StatTile T={T} label="cost saved" value={`$${(cache.usd_saved || 0).toFixed(2)}`} sub="vs recomputing on a cloud VLM · marginal cost → $0" accent="#56d364" />
          <StatTile T={T} label="containment" value={contain?.active ? 'ON' : '—'}
            sub={contain?.active ? `${contain.policy} policy · ${contain.denied_actions} exfil blocked` : 'scoutclaw sandbox'}
            accent={contain?.active ? T.acc : T.muted} />
          <StatTile T={T} label="heartbeats" value={runs.length} sub="autonomous decisions logged" accent="#79c0ff" />
        </div>

        {/* two columns */}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.35fr) minmax(0,1fr)', gap: 16, marginTop: 20, alignItems: 'start' }}>
          {/* runs feed */}
          <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: '16px 16px 8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 750 }}>Heartbeat feed</span>
              <button onClick={wake} disabled={ticking}
                style={{ background: T.acc, color: T.accText, border: 'none', borderRadius: 999, padding: '7px 16px', fontSize: 13, fontWeight: 800, cursor: ticking ? 'wait' : 'pointer', opacity: ticking ? .6 : 1 }}>
                {ticking ? 'waking…' : '⏻ wake now'}
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 460, overflowY: 'auto' }}>
              <AnimatePresence initial={false}>
                {runs.map(run => {
                  const st = ACTION_STYLE[run.decided?.action] || ACTION_STYLE.IDLE
                  const a = run.actions || {}
                  const detail = a.reused ? `⚡ ${a.concepts} widgets reused from cache (${a.source})`
                    : a.added?.length ? `+ added "${a.added[0].title?.slice(0, 46)}"`
                    : a.found?.length ? `scanned ${a.found.length} results`
                    : a.note || ''
                  return (
                    <motion.div key={run.id} layout
                      initial={{ opacity: 0, y: -12, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }}
                      transition={{ type: 'spring', stiffness: 240, damping: 24 }}
                      style={{ border: `1px solid ${T.line}`, borderLeft: `3px solid ${st.c}`, borderRadius: 10, padding: '10px 12px', background: theme === 'dark' ? '#0b0f08' : '#fbfdf8' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: mono, fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: st.c, background: st.c + '1f', borderRadius: 5, padding: '2px 7px' }}>{st.glyph} {st.label}</span>
                        <span style={{ fontFamily: mono, fontSize: 11, color: T.faint, marginLeft: 'auto' }}>{tclock(run.woke_at)}</span>
                      </div>
                      <div style={{ fontSize: 13, color: T.text, marginTop: 6, lineHeight: 1.4 }}>{run.decided?.why || '—'}</div>
                      {detail && <div style={{ fontFamily: mono, fontSize: 11.5, color: a.reused ? '#56d364' : T.muted, marginTop: 5 }}>{detail}</div>}
                    </motion.div>
                  )
                })}
              </AnimatePresence>
              {!runs.length && <div style={{ color: T.faint, fontSize: 13, padding: '20px 0', textAlign: 'center' }}>{err || 'no heartbeats yet — press wake now'}</div>}
            </div>
          </div>

          {/* curriculum + containment */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: '16px' }}>
              <div style={{ fontSize: 15, fontWeight: 750, marginBottom: 4 }}>Curriculum, building itself</div>
              <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 12 }}>the agent sequences a course, no human in the loop</div>
              {curriculum.map((c, i) => {
                const ready = c.state === 'ready'
                return (
                  <motion.div key={c.video_id || c.seq} layout initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}
                    style={{ display: 'flex', gap: 11, alignItems: 'flex-start', padding: '9px 0', borderTop: i ? `1px solid ${T.line}` : 'none' }}>
                    <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700, color: T.faint, marginTop: 2 }}>{String(c.seq).padStart(2, '0')}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, color: T.text, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</div>
                      {c.rationale && <div style={{ fontSize: 11, color: T.muted, marginTop: 2, lineHeight: 1.4 }}>{c.rationale}</div>}
                    </div>
                    <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: ready ? '#56d364' : '#ffab70', background: (ready ? '#56d364' : '#ffab70') + '1f', borderRadius: 5, padding: '2px 7px', flexShrink: 0 }}>
                      {ready ? '✓ ready' : '◷ planned'}
                    </span>
                  </motion.div>
                )
              })}
              {!curriculum.length && <div style={{ color: T.faint, fontSize: 13, padding: '10px 0' }}>empty — wake the agent to build it</div>}
            </div>

            {/* JOB2 — channels the agent watches for new uploads */}
            <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 15, fontWeight: 750 }}>Watching for new uploads</span>
                <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: '#ffab70', background: '#ffab701f', borderRadius: 5, padding: '2px 7px', marginLeft: 'auto' }}>📡 via Apify</span>
              </div>
              <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 12 }}>new upload on a watched channel → auto-builds its dashboard</div>
              {channels.map((ch, i) => (
                <div key={ch.channel_id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 0', borderTop: i ? `1px solid ${T.line}` : 'none' }}>
                  <span className="edu-pulse" style={{ width: 8, height: 8, borderRadius: 4, background: '#ffab70', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{ch.channel_id}</div>
                    <div style={{ fontFamily: mono, fontSize: 10.5, color: T.faint }}>
                      {ch.last_checked ? `last checked ${tclock(ch.last_checked)}` : 'not checked yet'}
                    </div>
                  </div>
                </div>
              ))}
              {!channels.length && <div style={{ color: T.faint, fontSize: 13, padding: '4px 0' }}>no channels watched yet</div>}
            </div>

            {/* curator — the library growing itself per genre */}
            {library.length > 0 && (
              <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 15, fontWeight: 750 }}>Library, growing itself</span>
                  <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: '#8ee23e', background: '#8ee23e1f', borderRadius: 5, padding: '2px 7px', marginLeft: 'auto' }}>📚 curator</span>
                </div>
                <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 12 }}>a 2nd agent finds + frames new videos per genre — cached for every learner</div>
                {(() => { const max = Math.max(...library.map(l => l.videos), 1); return library.map(l => (
                  <div key={l.genre} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '5px 0' }}>
                    <span style={{ fontSize: 12, color: T.text, width: 96, flexShrink: 0 }}>{GENRE_LABEL[l.genre] || l.genre}</span>
                    <div style={{ flex: 1, height: 8, background: T.line, borderRadius: 4, overflow: 'hidden' }}>
                      <motion.div initial={{ width: 0 }} animate={{ width: `${(l.videos / max) * 100}%` }} transition={{ type: 'spring', stiffness: 120, damping: 20 }}
                        style={{ height: '100%', background: '#8ee23e', borderRadius: 4 }} />
                    </div>
                    <span style={{ fontFamily: mono, fontSize: 11, color: T.faint, width: 20, textAlign: 'right' }}>{l.videos}</span>
                  </div>
                )) })()}
              </div>
            )}

            {/* containment strip */}
            <div style={{ background: T.panel, border: `1px solid ${contain?.active ? T.acc + '55' : T.line}`, borderRadius: 16, padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 15, fontWeight: 750 }}>Contained by OpenShell</span>
                <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: contain?.active ? T.acc : T.muted, background: (contain?.active ? T.acc : T.muted) + '1f', borderRadius: 5, padding: '2px 7px', marginLeft: 'auto' }}>
                  {contain?.active ? 'shields ready' : 'checking…'}
                </span>
              </div>
              <div style={{ fontSize: 11.5, color: T.muted, margin: '8px 0 10px' }}>egress allowlist — everything else is blocked + logged</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(contain?.allow || ['youtube', 'apify', 'supabase', 'local-inference']).map(h => (
                  <span key={h} style={{ fontFamily: mono, fontSize: 11, color: '#56d364', background: '#56d36418', border: '1px solid #56d36433', borderRadius: 6, padding: '3px 9px' }}>✓ {h}</span>
                ))}
                <span style={{ fontFamily: mono, fontSize: 11, color: '#e5484d', background: '#e5484d18', border: '1px solid #e5484d33', borderRadius: 6, padding: '3px 9px' }}>
                  ⛔ exfil · {contain?.denied_actions ?? 0} blocked
                </span>
              </div>
            </div>
          </div>
        </div>

        <div style={{ color: T.faint, fontSize: 12, fontFamily: mono, marginTop: 20, textAlign: 'center' }}>
          Nemotron Omni decides · yt-dlp / Apify act · Supabase persists + caches · OpenShell contains · every 60s, forever
        </div>
      </div>
    </div>
  )
}

// ---------- ?view=perf: live observability for /api/widget + /api/region ----------
function fmtMs(v) {
  if (v == null) return '—'
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`
}

function TimingBar({ ms, max, color }) {
  const w = max ? Math.min(100, (ms / max) * 100) : 0
  return (
    <div style={{ flex: 1, height: 6, background: '#22292f', borderRadius: 3, overflow: 'hidden', minWidth: 40 }}>
      <div style={{ width: `${w}%`, height: '100%', background: color, borderRadius: 3 }} />
    </div>
  )
}

function Sparkline({ values, width = 220, height = 32, color = '#8ee23e', threshold }) {
  if (!values || !values.length) return <svg width={width} height={height} />
  const max = Math.max(...values, threshold || 0, 1)
  const min = 0
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * width
    const y = height - ((v - min) / (max - min)) * height
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {threshold && (
        <line x1={0} x2={width} y1={height - (threshold / max) * height} y2={height - (threshold / max) * height}
          stroke="#e5484d" strokeDasharray="2,3" strokeWidth={1} opacity={0.55} />
      )}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  )
}

function PerfDashboard({ onExit }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('8kedu-theme') || 'dark')
  const T = THEMES[theme]
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [scope, setScope] = useState('mine')
  useEffect(() => { localStorage.setItem('8kedu-theme', theme); document.documentElement.style.background = T.solid }, [theme, T.solid])

  const load = async () => {
    try {
      const r = await fetch(`/agent/perf?scope=${scope}&limit=50`)
      const d = await r.json()
      if (d.ok) { setData(d); setErr(null) } else setErr(d.error || 'unknown error')
    } catch (e) { setErr('agent api offline — start agent/api.py') }
  }
  useEffect(() => { load(); const id = setInterval(load, 2000); return () => clearInterval(id) }, [scope])

  const events = data?.events || []
  const agg = data?.aggregates || {}
  const oldestFirst = [...events].reverse()
  const totalSpark = oldestFirst.map(e => e.t_total_ms || 0)
  const maxBar = Math.max(1, ...events.map(e => e.t_total_ms || 0))

  const kindCounts = {}
  events.forEach(e => {
    const k = e.widget_kind || 'unknown'
    kindCounts[k] = (kindCounts[k] || 0) + 1
  })
  const kindList = Object.entries(kindCounts).sort((a, b) => b[1] - a[1])

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
      <LandingStyles acc={T.acc} />
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '18px 24px 60px' }}>
        {/* top bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button onClick={onExit} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>← site</button>
            <Logo size={28} wordColor={T.text} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'flex', gap: 4, background: T.panel, border: `1px solid ${T.line}`, borderRadius: 999, padding: 3 }}>
              {['mine', 'all'].map(s => (
                <button key={s} onClick={() => setScope(s)}
                  style={{ background: scope === s ? T.acc : 'transparent', color: scope === s ? T.accText : T.text, border: 'none', borderRadius: 999, padding: '5px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                  {s === 'mine' ? `${data?.handle || 'me'}` : 'all users'}
                </button>
              ))}
            </div>
            <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: mono, fontSize: 12, color: T.muted }}>
              <motion.span animate={{ scale: [1, 1.5, 1], opacity: [1, .5, 1] }} transition={{ duration: 1.8, repeat: Infinity }}
                style={{ width: 9, height: 9, borderRadius: 5, background: err ? '#e5484d' : T.acc, display: 'inline-block' }} />
              {err ? 'offline' : 'polling live'}
            </span>
            <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} style={{ background: T.panel, border: `1px solid ${T.line}`, color: T.text, borderRadius: 999, padding: '7px 12px', fontSize: 13, cursor: 'pointer' }}>
              {theme === 'dark' ? '☀' : '☾'}
            </button>
          </div>
        </div>

        {/* header */}
        <div style={{ marginTop: 26 }}>
          <div style={{ fontFamily: mono, fontSize: 12, letterSpacing: '.2em', textTransform: 'uppercase', color: T.acc }}>perf, live</div>
          <h1 style={{ fontSize: 'clamp(26px,4vw,40px)', letterSpacing: '-.03em', margin: '8px 0 0', textWrap: 'balance' }}>
            time to first widget — every ask, every latency.
          </h1>
          <div style={{ color: T.sub, fontSize: 15, marginTop: 6 }}>
            target: <span style={{ color: T.text, fontWeight: 650 }}>p50 &lt; 5 s cold-miss</span> · red line on the sparkline marks the budget.
          </div>
        </div>

        {/* stat tiles */}
        <div style={{ display: 'flex', gap: 12, marginTop: 20, flexWrap: 'wrap' }}>
          <StatTile T={T} label="p50 total" value={fmtMs(agg.t_total_p50_ms)}
            sub={`across ${events.length} recent request${events.length === 1 ? '' : 's'}`}
            accent={agg.t_total_p50_ms == null ? T.muted : agg.t_total_p50_ms < 5000 ? T.acc : '#e5484d'} />
          <StatTile T={T} label="p90 total" value={fmtMs(agg.t_total_p90_ms)} sub="tail latency" accent="#79c0ff" />
          <StatTile T={T} label="p50 vlm-only" value={fmtMs(agg.t_backend_ask_p50_ms)} sub="cold-miss only · excludes cache hits" />
          <StatTile T={T} label="cache hit rate" value={`${Math.round((agg.cache_hit_rate || 0) * 100)}%`}
            sub={`${events.filter(e => e.cache_hit).length} of ${events.length} served from cache`} accent="#56d364" />
          <StatTile T={T} label="requests" value={events.length} sub="in the last 50" accent="#79c0ff" />
        </div>

        {/* sparkline + widget-kind mix */}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)', gap: 16, marginTop: 20, alignItems: 'stretch' }}>
          <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>total-ms over last {oldestFirst.length}</div>
            <Sparkline values={totalSpark} width={520} height={64} color={T.acc} threshold={5000} />
            <div style={{ display: 'flex', justifyContent: 'space-between', color: T.muted, fontFamily: mono, fontSize: 11, marginTop: 6 }}>
              <span>oldest</span><span>newest</span>
            </div>
          </div>
          <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>widget mix</div>
            {kindList.length === 0 && <div style={{ color: T.faint, fontSize: 13 }}>no events yet</div>}
            {kindList.map(([k, n]) => (
              <div key={k} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '3px 0' }}>
                <span style={{ fontSize: 12, color: T.text, width: 96, flexShrink: 0 }}>{k}</span>
                <div style={{ flex: 1, height: 8, background: T.line, borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${(n / events.length) * 100}%`, height: '100%', background: k === 'none' ? T.muted : k === 'answer' ? '#79c0ff' : '#8ee23e', borderRadius: 4 }} />
                </div>
                <span style={{ fontFamily: mono, fontSize: 11, color: T.faint, width: 24, textAlign: 'right' }}>{n}</span>
              </div>
            ))}
          </div>
        </div>

        {/* events table */}
        <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 16, padding: '16px', marginTop: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 750, marginBottom: 12 }}>Recent events</div>
          {events.length === 0 && <div style={{ color: T.faint, fontSize: 13, padding: '10px 0' }}>{err || 'no widget mints yet — go to a lecture and click "make it interactive"'}</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 520, overflowY: 'auto' }}>
            {events.map(e => {
              const overBudget = (e.t_total_ms || 0) > 5000
              const time = e.created_at ? new Date(e.created_at).toLocaleTimeString() : ''
              return (
                <div key={e.id} style={{ display: 'grid', gridTemplateColumns: '68px 60px 74px 40px 1fr 60px', gap: 10, alignItems: 'center', padding: '8px 10px', border: `1px solid ${overBudget ? '#e5484d55' : T.line}`, borderLeft: `3px solid ${overBudget ? '#e5484d' : e.cache_hit ? '#56d364' : e.spec_valid ? T.acc : '#ffab70'}`, borderRadius: 8, background: theme === 'dark' ? '#0b0f08' : '#fbfdf8' }}>
                  <span style={{ fontFamily: mono, fontSize: 11, color: T.faint }}>{time}</span>
                  <span style={{ fontFamily: mono, fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', color: e.kind === 'region' ? '#79c0ff' : T.acc, background: (e.kind === 'region' ? '#79c0ff' : T.acc) + '1f', borderRadius: 5, padding: '2px 6px', textAlign: 'center' }}>{e.kind}</span>
                  <span style={{ fontFamily: mono, fontSize: 11, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.widget_kind || '—'}</span>
                  <span title={e.cache_hit ? 'cache hit' : 'cache miss'} style={{ fontFamily: mono, fontSize: 12, textAlign: 'center' }}>
                    {e.cache_hit ? '⚡' : '·'}
                  </span>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span title="cache lookup" style={{ fontFamily: mono, fontSize: 10, color: T.faint, width: 34 }}>{e.t_cache_lookup_ms ?? 0}</span>
                    <TimingBar ms={e.t_backend_ask_ms || 0} max={maxBar} color={overBudget ? '#e5484d' : '#8ee23e'} />
                    <span title="VLM (backend.ask)" style={{ fontFamily: mono, fontSize: 10.5, color: overBudget ? '#e5484d' : T.text, width: 62, textAlign: 'right' }}>{fmtMs(e.t_backend_ask_ms)}</span>
                  </div>
                  <span style={{ fontFamily: mono, fontSize: 11.5, fontWeight: 700, color: overBudget ? '#e5484d' : T.text, textAlign: 'right' }}>{fmtMs(e.t_total_ms)}</span>
                </div>
              )
            })}
          </div>
        </div>

        <div style={{ color: T.faint, fontSize: 12, fontFamily: mono, marginTop: 20, textAlign: 'center' }}>
          instrumented in serve.py · non-blocking write to widget_events · polled every 2 s
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState(() => new URLSearchParams(location.search).get('view'))
  const [videoId, setVideoId] = useState(() => {
    const q = new URLSearchParams(location.search).get('v')
    if (q) return q
    return specFromHash() ? parseVideoId(DEFAULT_URL) : null // remix links open the default lecture
  })
  const [role, setRole] = useState(() => new URLSearchParams(location.search).get('role'))
  const open = (id, r) => {
    history.pushState({}, '', `?v=${id}${r ? `&role=${r}` : ''}`)
    setVideoId(id)
    setRole(r ?? null)
  }
  useEffect(() => {
    const sync = () => {
      const p = new URLSearchParams(location.search)
      setVideoId(p.get('v'))
      setRole(p.get('role'))
      setView(p.get('view'))
    }
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const exitView = () => { history.pushState({}, '', location.pathname); setView(null) }
  if (view === 'agent') return <AgentDashboard onExit={exitView} />
  if (view === 'perf') return <PerfDashboard onExit={exitView} />
  if (view === 'learn') return <LearnView onExit={exitView} onOpen={open} />
  if (view === 'community') return <CommunityView onExit={exitView} onOpen={open} />
  return videoId ? <Lecture key={`${videoId}-${role}`} videoId={videoId} role={role} /> : <Landing onOpen={open} />
}
