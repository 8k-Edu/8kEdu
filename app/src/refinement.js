export const buildRefinementSource = (spec, liveParams) => {
  const params = { ...(spec.params ?? {}), ...(liveParams ?? {}) }
  return { ...spec, params }
}

export const nextRefinementRevision = (revision, outcome) => outcome === 'success' ? revision + 1 : revision

export const widgetInstanceKey = (spec, revision) => `${spec.time}-${spec.widget}-${revision}`

export const buildRefinementRequest = ({ spec, liveParams, instruction, text, time, video, cloud, replaces, replacesKey }) => ({
  text,
  time: spec.time ?? time,
  ask: instruction,
  video,
  cloud,
  current_spec: buildRefinementSource(spec, liveParams),
  ...(replaces ? { replaces } : { replaces_key: replacesKey }),
})
