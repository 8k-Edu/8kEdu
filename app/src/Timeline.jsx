import React from 'react'
import {
  chapterTimelineRange,
  formatTimelineTime,
  timelinePlayheadPercent,
  timelineTickAppearance,
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
  const playhead = timelinePlayheadPercent(time, duration)

  return (
    <div data-timeline-track style={{
      position: 'relative', height: 30, marginTop: 10,
      background: 'linear-gradient(180deg, #161b22, #10141a)',
      borderRadius: 999, border: '1px solid #30363d', overflow: 'hidden',
    }}>
      <div data-timeline-plot style={{ position: 'absolute', inset: '0 8px' }}>
        {chapters.map((chapter, index) => {
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
        {concepts.map((concept, index) => {
          const left = timelineTickPercent(concept.time, duration)
          if (left == null) return null
          const isActive = concept === active
          const appearance = timelineTickAppearance(concept, isActive, typeColors)
          return (
            <button key={`${concept.time}-${index}`} data-timeline-tick
              data-timeline-percent={left} data-timeline-active={isActive || undefined}
              className="tl-tick"
              title={`${concept.title} · ${typeIcons[concept.widget] ?? ''}`}
              aria-label={`Jump to ${concept.title ?? 'widget'} at ${formatTimelineTime(concept.time)}`}
              onClick={() => onPick?.(concept)}
              style={{
                position: 'absolute', left: `${left}%`, top: '50%', width: 4,
                border: 'none', padding: 0, borderRadius: 99,
                height: isActive ? 22 : concept.user_made ? 18 : 13,
                background: appearance.background,
                opacity: isActive ? 1 : 0.65,
                transform: 'translate(-50%, -50%)',
                boxShadow: appearance.boxShadow,
                transition: 'height .15s, opacity .15s', zIndex: 2,
              }} />
          )
        })}
        {playhead != null && (
          <div data-timeline-playhead data-timeline-percent={playhead} style={{
            position: 'absolute', left: `${playhead}%`, top: 0, bottom: 0, width: 2,
            background: '#f85149', boxShadow: '0 0 6px #f8514988',
            transform: 'translateX(-50%)', pointerEvents: 'none', zIndex: 3,
          }} />
        )}
      </div>
    </div>
  )
}
