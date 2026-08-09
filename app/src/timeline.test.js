import { after, before, describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import react from '@vitejs/plugin-react'
import { createServer } from 'vite'
import {
  chapterTimelineRange,
  formatTimelineTime,
  latestPlayerDuration,
  resolveTimelineDuration,
  timelinePlayheadPercent,
  timelineTickAppearance,
  timelineTickPercent,
} from './timeline.js'

const cues = [{ end: 200 }]
const chapters = [{ end: 150 }]

test('ingest metadata wins and observed coverage otherwise uses the widest endpoint', () => {
  const cases = [
    [{ ingestDuration: 250, playerDuration: 300, cues, chapters }, 250],
    [{ playerDuration: 300, cues, chapters }, 300],
    [{ playerDuration: 175, cues, chapters }, 200],
    [{ playerDuration: 175, cues: [{ end: 100 }], chapters: [{ end: 225 }] }, 225],
    [{ playerDuration: 300, cues: [], chapters: [] }, 300],
    [{ playerDuration: null, cues, chapters }, 200],
    [{ playerDuration: null, cues: [], chapters }, 150],
    [{ playerDuration: null, cues: [], chapters: [] }, null],
  ]
  for (const [input, expected] of cases) {
    assert.equal(resolveTimelineDuration(input), expected)
  }
})

test('invalid player readings retain the artifact fallback', () => {
  for (const playerDuration of [0, -1, NaN, Infinity, -Infinity, undefined]) {
    assert.equal(resolveTimelineDuration({ playerDuration, cues, chapters }), 200)
  }
})

test('player duration grows monotonically across transient readings', () => {
  assert.equal(latestPlayerDuration(null, 30), 30)
  assert.equal(latestPlayerDuration(30, 331), 331)
  assert.equal(latestPlayerDuration(331, 30), 331)
  assert.equal(latestPlayerDuration(331, 0), 331)
  assert.equal(latestPlayerDuration(null, NaN), null)
})

test('artifact-shaped inputs resolve their full observed spans', () => {
  assert.equal(resolveTimelineDuration({ cues: [{ end: 331.84 }], chapters: [{ end: 331 }] }), 331.84)
  assert.equal(resolveTimelineDuration({ cues: [{ end: 2111.12 }] }), 2111.12)
  assert.equal(resolveTimelineDuration({ cues: [{ end: 591.82 }], chapters: [{ end: 591 }] }), 591.82)
  assert.equal(resolveTimelineDuration({ chapters: [{ start: 400, end: null }] }), 400)
})

test('ticks and playhead clamp to the timeline range', () => {
  assert.equal(timelineTickPercent(0, 300), 0)
  assert.equal(timelineTickPercent(300, 300), 100)
  assert.equal(timelineTickPercent(-1, 300), 0)
  assert.equal(timelineTickPercent(301, 300), 100)
  assert.equal(timelinePlayheadPercent(-1, 300), 0)
  assert.equal(timelinePlayheadPercent(301, 300), 100)
  assert.equal(timelinePlayheadPercent(10, null), null)
})

test('chapter endpoints clamp independently with non-negative widths', () => {
  assert.deepEqual(chapterTimelineRange({ start: 400, end: 500 }, 300), { left: 100, width: 0 })
  const missingEnd = chapterTimelineRange({ start: 250, end: null }, 300)
  assert.ok(Math.abs(missingEnd.left - (250 / 3)) < 1e-10)
  assert.ok(Math.abs(missingEnd.width - (50 / 3)) < 1e-10)
  const negativeStart = chapterTimelineRange({ start: -20, end: 50 }, 300)
  assert.equal(negativeStart.left, 0)
  assert.ok(Math.abs(negativeStart.width - (50 / 3)) < 1e-10)
  const reversed = chapterTimelineRange({ start: 200, end: 100 }, 300)
  assert.ok(Math.abs(reversed.left - (200 / 3)) < 1e-10)
  assert.equal(reversed.width, 0)
})

test('tick appearance preserves distinct body and active glow fallbacks', () => {
  const concept = { widget: 'spreadsheet' }
  assert.deepEqual(timelineTickAppearance(concept, true), {
    background: '#6e7681',
    boxShadow: '0 0 10px #2f81f7',
  })
  assert.deepEqual(timelineTickAppearance(concept, true, { spreadsheet: '#56d364' }), {
    background: '#56d364',
    boxShadow: '0 0 10px #56d364',
  })
})

test('timeline timestamps are formatted for accessible labels', () => {
  assert.equal(formatTimelineTime(0), '0:00')
  assert.equal(formatTimelineTime(70.3), '1:10')
  assert.equal(formatTimelineTime(6689.1), '1:51:29')
})

const occurrences = (text, pattern) => (text.match(pattern) ?? []).length

describe('rendered timeline', () => {
  let vite
  let Timeline

  before(async () => {
    const appRoot = fileURLToPath(new URL('..', import.meta.url))
    vite = await createServer({
      root: appRoot,
      configFile: false,
      plugins: [react()],
      server: { middlewareMode: true },
      appType: 'custom',
      logLevel: 'silent',
    })
    ;({ Timeline } = await vite.ssrLoadModule('/src/Timeline.jsx'))
  })

  after(async () => {
    await vite?.close()
  })

  const renderTimeline = (props) => renderToStaticMarkup(React.createElement(Timeline, props))

  test('missing durations render only the track and endpoint caps', () => {
    for (const duration of [null, undefined, 0]) {
      const markup = renderTimeline({
        duration,
        time: 30,
        chapters: [{ start: 0, end: 100 }],
        concepts: [{ time: 0, title: 'Start', widget: 'spreadsheet' }],
      })
      assert.doesNotMatch(markup, /NaN|Infinity/)
      assert.match(markup, /data-timeline-track/)
      assert.equal(occurrences(markup, /data-timeline-cap=/g), 2)
      assert.doesNotMatch(markup, /data-timeline-tick/)
      assert.doesNotMatch(markup, /data-timeline-playhead/)
      assert.doesNotMatch(markup, /data-timeline-chapter/)
    }
  })

  test('endpoint ticks expose scoped positions and the active branch', () => {
    const start = { time: 0, title: 'Start', widget: 'spreadsheet' }
    const end = { time: 100, title: 'End', widget: 'spreadsheet' }
    const markup = renderTimeline({
      duration: 100,
      time: 50,
      active: start,
      concepts: [start, end],
    })
    const ticks = markup.match(/<button[^>]*data-timeline-tick[^>]*>/g) ?? []
    assert.doesNotMatch(markup, /NaN|Infinity/)
    assert.equal(ticks.length, 2)
    assert.match(ticks[0], /data-timeline-percent="0"/)
    assert.match(ticks[0], /data-timeline-active="true"/)
    assert.match(ticks[0], /aria-label="Jump to Start at 0:00"/)
    assert.match(ticks[1], /data-timeline-percent="100"/)
    assert.doesNotMatch(ticks[1], /data-timeline-active/)
  })
})
