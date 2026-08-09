const MAX_SOURCE_CHARS = 12000

const encodedSize = (value) => JSON.stringify(value).length

const boundedSource = (spec, params) => {
  if (spec.widget !== 'notebook' && spec.widget !== 'spreadsheet') return { ...spec, params }
  const cells = params?.cells
  if (!Array.isArray(cells)) return { ...spec, params }
  const kept = []
  for (const cell of cells) {
    const next = { ...spec, params: { ...params, cells: [...kept, cell] } }
    if (encodedSize(next) > MAX_SOURCE_CHARS) break
    kept.push(cell)
  }
  return { ...spec, params: { ...params, cells: kept } }
}

export const buildRefinementSource = (spec, liveParams) => {
  const params = { ...(spec.params ?? {}), ...(liveParams ?? {}) }
  return boundedSource(spec, params)
}

export const buildRefinementRequest = ({ spec, liveParams, instruction, text, time, video, cloud, replaces, replacesKey }) => ({
  text,
  time: spec.time ?? time,
  ask: instruction,
  video,
  cloud,
  current_spec: buildRefinementSource(spec, liveParams),
  ...(replaces ? { replaces } : { replaces_key: replacesKey }),
})
