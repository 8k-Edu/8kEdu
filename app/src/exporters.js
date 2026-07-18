// Export selected concepts as .ipynb / .md / printable deck — all client-side.

const fmt = (t) => {
  t = Math.max(0, Math.floor(t))
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

// JS expr (our function_plot dialect) → numpy
const jsToPy = (expr) =>
  expr
    .replaceAll('Math.pow', 'np.power')
    .replaceAll('Math.max', 'np.maximum')
    .replaceAll('Math.min', 'np.minimum')
    .replaceAll('Math.PI', 'np.pi')
    .replaceAll('Math.E', 'np.e')
    .replace(/Math\.(\w+)/g, 'np.$1')

const sliderConsts = (sliders = []) =>
  sliders.map(s => `${s.name} = ${s.value}  # slider ${s.min}..${s.max}`).join('\n')

// python cells for one concept
function conceptToPython(c) {
  const p = c.params ?? {}
  const np = (m) => `np.array(${JSON.stringify(m)})`
  switch (c.widget) {
    case 'notebook':
      return [
        ...(p.sliders?.length ? [sliderConsts(p.sliders)] : []),
        ...(p.cells ?? []),
      ]
    case 'matrix_mul':
      return [[
        'import numpy as np',
        `A = ${np(p.a ?? [[1, 0], [0, 1]])}`,
        `B = ${np(p.b ?? [[1, 0], [0, 1]])}`,
        'print("A @ B =")', 'print(A @ B)',
      ].join('\n')]
    case 'attention':
      return [[
        'import numpy as np',
        `Q = ${np(p.q ?? [[1, 0], [0, 1]])}`,
        `K = ${np(p.k ?? [[1, 0], [0, 1]])}`,
        `temperature = ${p.temperature ?? 1}`,
        'scores = Q @ K.T / np.sqrt(Q.shape[1])',
        'e = np.exp((scores - scores.max(1, keepdims=True)) / temperature)',
        'weights = e / e.sum(1, keepdims=True)',
        'print(np.round(weights, 3))',
        '',
        'import matplotlib.pyplot as plt',
        "plt.imshow(weights, cmap='Greens'); plt.title('attention weights'); plt.colorbar(); plt.show()",
      ].join('\n')]
    case 'softmax':
      return [[
        'import numpy as np',
        `logits = np.array(${JSON.stringify(p.logits ?? [2, 1, 0, -1])})`,
        `temperature = ${p.temperature ?? 1}`,
        'e = np.exp((logits - logits.max()) / temperature)',
        'probs = e / e.sum()',
        'print(np.round(probs, 3))',
        '',
        'import matplotlib.pyplot as plt',
        'plt.bar(range(len(probs)), probs); plt.title(f"softmax @ T={temperature}"); plt.show()',
      ].join('\n')]
    case 'function_plot': {
      const consts = sliderConsts(p.sliders)
      return [[
        'import numpy as np',
        'import matplotlib.pyplot as plt',
        ...(consts ? [consts] : []),
        'x = np.linspace(-6, 6, 400)',
        `y = ${jsToPy(p.expr ?? 'np.sin(x)')}`,
        `plt.plot(x, y); plt.title(${JSON.stringify(p.expr ?? '')}); plt.grid(alpha=.3); plt.show()`,
      ].join('\n')]
    }
    default:
      return [`# ${c.widget} spec (render in EduClaw)\nspec = ${JSON.stringify(c.params, null, 2)}`]
  }
}

const ytLink = (videoId, t) => `https://youtu.be/${videoId}?t=${Math.floor(t)}`

export function buildNotebook(concepts, videoId, title) {
  const cells = [
    md(`# ${title}\n\nInteractive moments extracted from [the lecture](https://youtu.be/${videoId}) with **EduClaw** — each section links back to the exact moment.`),
  ]
  for (const c of concepts) {
    cells.push(md(`## ${c.title}\n\n*${c.explanation ?? ''}*\n\n[▶ watch this moment (${fmt(c.time)})](${ytLink(videoId, c.time)})`))
    for (const src of conceptToPython(c)) cells.push(code(src))
  }
  const nb = {
    nbformat: 4, nbformat_minor: 5,
    metadata: { kernelspec: { display_name: 'Python 3', language: 'python', name: 'python3' } },
    cells,
  }
  return JSON.stringify(nb, null, 1)

  function md(source) { return { cell_type: 'markdown', metadata: {}, source } }
  function code(source) { return { cell_type: 'code', metadata: {}, execution_count: null, outputs: [], source } }
}

export function buildMarkdown(concepts, videoId, title, origin) {
  const lines = [
    `# ${title}`, '',
    `*Interactive study notes from [the lecture](https://youtu.be/${videoId}), extracted with EduClaw — every figure is a live widget you can remix.*`, '',
  ]
  for (const c of concepts) {
    lines.push(`## ${fmt(c.time)} — ${c.title}`, '')
    if (c.frame && c.frame !== 'stub') lines.push(`![frame at ${fmt(c.time)}](frames/${c.frame})`, '')
    lines.push(c.explanation ?? '', '')
    for (const src of conceptToPython(c)) lines.push('```python', src, '```', '')
    const spec = btoa(unescape(encodeURIComponent(JSON.stringify(c))))
    lines.push(`[▶ watch this moment](${ytLink(videoId, c.time)}) · [🔁 open the live widget](${origin}/?v=${videoId}#s=${spec})`, '')
  }
  lines.push('---', '', '*Made with EduClaw — lectures you can touch.*')
  return lines.join('\n')
}

export function buildDeckHtml(concepts, videoId, title) {
  const slide = (c) => `
  <section class="slide">
    <div class="k">${fmt(c.time)} · ${c.widget}</div>
    <h2>${esc(c.title)}</h2>
    ${c.frame && c.frame !== 'stub' ? `<img src="/frames/${c.frame}" alt="">` : ''}
    <p>${esc(c.explanation ?? '')}</p>
    <div class="link">youtu.be/${videoId}?t=${Math.floor(c.time)}</div>
  </section>`
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #fff; color: #111; }
  .slide { page-break-after: always; min-height: 92vh; padding: 6vh 8vw; display: flex; flex-direction: column; justify-content: center; gap: 14px; }
  .k { color: #888; font-size: 13px; letter-spacing: .05em; text-transform: uppercase; }
  h2 { font-size: 34px; margin: 0; }
  img { max-width: 78%; border-radius: 10px; border: 1px solid #ddd; }
  p { font-size: 18px; line-height: 1.5; max-width: 60ch; }
  .link { color: #666; font-size: 13px; font-family: ui-monospace, monospace; }
  .cover h1 { font-size: 52px; margin: 0; }
  @media print { .hint { display: none } }
  .hint { position: fixed; top: 10px; right: 12px; background: #111; color: #fff; padding: 8px 14px; border-radius: 8px; font-size: 13px; }
</style></head><body>
<div class="hint">⌘P → save as PDF</div>
<section class="slide cover"><div class="k">EduClaw deck</div><h1>${esc(title)}</h1>
<p>${concepts.length} interactive moments from <b>youtu.be/${videoId}</b> — live versions in EduClaw.</p></section>
${concepts.map(slide).join('\n')}
</body></html>`
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;') }
}

export function download(filename, content, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
