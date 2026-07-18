import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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

// the showcase shelf — videos with pipeline data available, grouped by theme
const CATEGORIES = [
  {
    name: 'AI & STEM', icon: '🧠',
    videos: [
      { id: 'kCc8FmEb1nY', title: "Karpathy — Let's build GPT from scratch" },
    ],
  },
  {
    name: 'Real estate', icon: '🏠',
    videos: [
      { id: 'BV6i8MNZ-BI', title: 'How to Buy your First House [Noob vs Pro] — $0 to Millionaire' },
    ],
  },
  {
    name: 'Fintech & markets', icon: '💰',
    videos: [
      { id: '3FZipnSI_po', title: 'Andrei Jikh — Japan Just Broke the Global Economy' },
    ],
  },
]
const VIDEOS = CATEGORIES.flatMap(c => c.videos.map(v => ({ ...v, tag: c.name })))
const INGESTED = VIDEOS.map(v => v.id)

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

function Landing({ onOpen }) {
  const [url, setUrl] = useState(DEFAULT_URL)
  const [err, setErr] = useState(null)
  const go = () => {
    const id = parseVideoId(url.trim())
    if (!id) { setErr('paste a YouTube link (or 11-char video id)'); return }
    onOpen(id)
  }
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ width: 640, maxWidth: '94vw', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div>
          <h1 style={{ fontSize: 40, letterSpacing: -1 }}>8kEdu</h1>
          <div style={{ color: '#e6edf3', fontSize: 18, marginTop: 8, fontWeight: 600 }}>
            YouTube video → interactive learning dashboard
          </div>
          <div style={{ color: '#8b949e', fontSize: 15, marginTop: 6, lineHeight: 1.5 }}>
            Paste any lecture. Every figure, equation, and code block becomes a live widget you can tweak, run, and remix — on any topic.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <input value={url} onChange={e => { setUrl(e.target.value); setErr(null) }}
            onKeyDown={e => e.key === 'Enter' && go()}
            placeholder="https://www.youtube.com/watch?v=…"
            style={{
              flex: 1, background: '#161b22', color: '#e6edf3', border: '1px solid #30363d',
              borderRadius: 10, padding: '13px 14px', fontSize: 14, textAlign: 'left',
            }} />
          <button onClick={go} style={{
            background: '#2f81f7', color: 'white', border: 'none', borderRadius: 10,
            padding: '13px 22px', fontSize: 15, fontWeight: 700,
          }}>open</button>
        </div>
        {err && <div style={{ color: '#f85149', fontSize: 13 }}>{err}</div>}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ color: '#8b949e', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.05em' }}>
            ready to touch — any topic, not just code
          </div>
          {CATEGORIES.map(cat => (
            <div key={cat.name}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 14.5, fontWeight: 700, color: '#e6edf3' }}>{cat.icon} {cat.name}</span>
                <span style={{ fontSize: 11.5, color: '#484f58' }}>{cat.videos.length} lecture{cat.videos.length > 1 ? 's' : ''}</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
                {cat.videos.map(v => (
                  <button key={v.id} onClick={() => onOpen(v.id)} style={{
                    textAlign: 'left', background: '#161b22', border: '1px solid #30363d', borderRadius: 12,
                    padding: 0, overflow: 'hidden', cursor: 'pointer',
                  }}>
                    <img src={`https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`} alt=""
                      style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }} />
                    <div style={{ padding: '8px 10px 10px' }}>
                      <span style={{ fontSize: 12.5, color: '#e6edf3', lineHeight: 1.4 }}>{v.title}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginTop: 10 }}>
          {[
            ['student', '🎓', 'Student', 'Watch — widgets appear beside the video. Check the best ones → export a Jupyter notebook. Tonight\'s lab, from tonight\'s lecture.'],
            ['teacher', '👩‍🏫', 'Teacher', 'Opens on ☰ moments — pick the arc of the lesson → one-click deck (⌘P → PDF). Every slide links to its live widget for in-class play.'],
            ['creator', '✍️', 'Creator / Writer', 'Select a thread of moments → Markdown with keyframes, runnable code and remix links. Paste into Medium / Substack / your editor.'],
            ['researcher', '🔬', 'Researcher', 'Select any sentence, mint the widget you need. Coming soon: trace a concept across lectures, citation export.'],
          ].map(([key, icon, title, text]) => (
            <button key={key} onClick={() => onOpen('kCc8FmEb1nY', key)} style={{
              textAlign: 'left', background: '#161b22', border: '1px solid #30363d', borderRadius: 12,
              padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 6, cursor: 'pointer',
            }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#e6edf3' }}>{icon} {title}</span>
              <span style={{ fontSize: 12.5, color: '#8b949e', lineHeight: 1.55 }}>{text}</span>
            </button>
          ))}
        </div>
        <div style={{ color: '#484f58', fontSize: 12 }}>
          pipeline: yt-dlp → keyframes → open VLM (local MLX / vLLM / BYOK) → spec JSON → live widgets · python runs in-browser via pyodide · remix = a URL
        </div>
      </div>
    </div>
  )
}

export default function App() {
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
    }
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  return videoId ? <Lecture key={`${videoId}-${role}`} videoId={videoId} role={role} /> : <Landing onOpen={open} />
}
