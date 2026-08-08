import React from 'react'
import {
  chapterTimelineRange,
  hasTimelineDuration,
  timelinePlayheadPercent,
  timelineTickPercent,
} from './timeline.js'

export function Timeline({
  chapters = [],
  concepts = [],
  duration,
  time,
  active,
  onPick,
  typeIcons = {},
  typeColors = {},
}) {
  const hasDuration = hasTimelineDuration(duration)
  const playhead = timelinePlayheadPercent(time, duration)

  return (
    <div data-timeline-track style={{
      position: 'relative', height: 30, marginTop: 10,
      background: 'linear-gradient(180deg, #161b22, #10141a)',
      borderRadius: 999, border: '1px solid #30363d', overflow: 'hidden',
    }}>
      <div data-timeline-plot style={{ position: 'absolute', inset: '0 8px' }}>
        {hasDuration && chapters.map((chapter, index) => {
          if (index % 2 === 0) return null
          const range = chapterTimelineRange(chapter, duration)
          if (!range) return null
          return (
            <div key={index} data-timeline-chapter style={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${range.left}%`, width: `${range.width}%`,
              background: '#ffffff05', pointerEvents: 'none',
            }} />
          )
        })}
        <div data-timeline-cap="start" style={{
          position: 'absolute', left: 0, top: 5, bottom: 5, width: 1,
          background: '#6e7681', opacity: 0.8, pointerEvents: 'none', zIndex: 1,
        }} />
        <div data-timeline-cap="end" style={{
          position: 'absolute', right: 0, top: 5, bottom: 5, width: 1,
          background: '#6e7681', opacity: 0.8, pointerEvents: 'none', zIndex: 1,
        }} />
        {hasDuration && concepts.map((concept, index) => {
          const left = timelineTickPercent(concept.time, duration)
          if (left == null) return null
          const isActive = concept === active
          const color = typeColors[concept.widget] ?? '#6e7681'
          return (
            <button key={`${concept.time}-${index}`} data-timeline-tick className="tl-tick"
              title={`${concept.title} · ${typeIcons[concept.widget] ?? ''}`}
              aria-label={`Jump to ${concept.title ?? 'widget'} at ${concept.time} seconds`}
              onClick={() => onPick?.(concept)}
              style={{
                position: 'absolute', left: `${left}%`, top: '50%', width: 4,
                border: 'none', padding: 0, borderRadius: 99,
                height: isActive ? 22 : concept.user_made ? 18 : 13,
                background: concept.user_made ? '#e3b341' : color,
                opacity: isActive ? 1 : 0.65,
                transform: 'translate(-50%, -50%)',
                boxShadow: isActive ? `0 0 10px ${color}` : 'none',
                transition: 'height .15s, opacity .15s', zIndex: 3,
              }} />
          )
        })}
        {playhead != null && (
          <div data-timeline-playhead style={{
            position: 'absolute', left: `${playhead}%`, top: 0, bottom: 0, width: 2,
            background: '#f85149', boxShadow: '0 0 6px #f8514988',
            transform: 'translateX(-50%)', pointerEvents: 'none', zIndex: 2,
          }} />
        )}
      </div>
    </div>
  )
}
