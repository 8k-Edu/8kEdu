const isFinitePositive = (value) => Number.isFinite(value) && value > 0

const maxEndpoint = (items) => {
  const endpoints = items
    .map(item => item?.end ?? item?.start)
    .filter(isFinitePositive)
  return endpoints.length ? Math.max(...endpoints) : null
}

export function resolveTimelineDuration({
  ingestDuration,
  playerDuration,
  cues = [],
  chapters = [],
} = {}) {
  if (isFinitePositive(ingestDuration)) return ingestDuration
  const cueEnd = maxEndpoint(Array.isArray(cues) ? cues : [])
  const chapterEnd = maxEndpoint(Array.isArray(chapters) ? chapters : [])
  const endpoints = [playerDuration, cueEnd, chapterEnd].filter(isFinitePositive)
  return endpoints.length ? Math.max(...endpoints) : null
}

export function hasTimelineDuration(duration) {
  return isFinitePositive(duration)
}

export function latestPlayerDuration(currentDuration, nextDuration) {
  if (!isFinitePositive(nextDuration)) return isFinitePositive(currentDuration) ? currentDuration : null
  if (!isFinitePositive(currentDuration)) return nextDuration
  return Math.max(currentDuration, nextDuration)
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

export function timelineTickPercent(time, duration) {
  if (!hasTimelineDuration(duration) || !Number.isFinite(time)) return null
  return (clamp(time, 0, duration) / duration) * 100
}

export function timelinePlayheadPercent(time, duration) {
  if (!hasTimelineDuration(duration) || !Number.isFinite(time)) return null
  return (clamp(time, 0, duration) / duration) * 100
}

export function chapterTimelineRange(chapter, duration) {
  if (!hasTimelineDuration(duration) || !Number.isFinite(chapter?.start)) return null
  const rawEnd = chapter.end == null ? duration : chapter.end
  if (!Number.isFinite(rawEnd)) return null
  const start = clamp(chapter.start, 0, duration)
  const end = clamp(rawEnd, 0, duration)
  return {
    left: (start / duration) * 100,
    width: (Math.max(0, end - start) / duration) * 100,
  }
}

export function timelineTickAppearance(concept, isActive, typeColors = {}) {
  const typeColor = typeColors[concept.widget]
  return {
    background: concept.user_made ? '#e3b341' : (typeColor ?? '#6e7681'),
    boxShadow: isActive ? `0 0 10px ${typeColor ?? '#2f81f7'}` : 'none',
  }
}

const asArray = (value) => (Array.isArray(value) ? value : [])

const fallbackKey = (concept) => `${concept?.widget}@${Math.round(concept?.time ?? 0)}`

export function conceptKey(concept) {
  return concept?.id ?? fallbackKey(concept)
}

// Pipeline concepts (data/<video>/concepts.json) carry no id, so a saved widget claims the
// slot it occupies by widget+second, or by an explicit replaces_key when a refinement
// changed the widget type. See agent/widget_store.py for where the ids come from.
export function mergeConcepts(base, saved) {
  const savedConcepts = asArray(saved)
  const shadowed = new Set()
  for (const concept of savedConcepts) {
    shadowed.add(fallbackKey(concept))
    if (concept.replaces_key) shadowed.add(concept.replaces_key)
  }
  const byKey = new Map()
  for (const concept of asArray(base)) {
    if (shadowed.has(fallbackKey(concept)) || shadowed.has(conceptKey(concept))) continue
    byKey.set(conceptKey(concept), concept)
  }
  for (const concept of savedConcepts) byKey.set(conceptKey(concept), concept)
  return [...byKey.values()].sort((a, b) => (a.time ?? 0) - (b.time ?? 0))
}

export function formatTimelineTime(time) {
  const seconds = Math.max(0, Math.floor(Number.isFinite(time) ? time : 0))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}
