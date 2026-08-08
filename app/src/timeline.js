const isFinitePositive = (value) => Number.isFinite(value) && value > 0

const maxEndpoint = (items) => {
  const endpoints = items
    .map(item => item?.end)
    .filter(isFinitePositive)
  return endpoints.length ? Math.max(...endpoints) : null
}

export function resolveTimelineDuration(playerDuration, cues = [], chapters = []) {
  if (isFinitePositive(playerDuration)) return playerDuration
  const cueEnd = maxEndpoint(Array.isArray(cues) ? cues : [])
  const chapterEnd = maxEndpoint(Array.isArray(chapters) ? chapters : [])
  const endpoints = [cueEnd, chapterEnd].filter(isFinitePositive)
  return endpoints.length ? Math.max(...endpoints) : null
}

export function hasTimelineDuration(duration) {
  return isFinitePositive(duration)
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

export function timelineTickPercent(time, duration) {
  if (!hasTimelineDuration(duration) || !Number.isFinite(time) || time < 0 || time > duration) return null
  return (time / duration) * 100
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
