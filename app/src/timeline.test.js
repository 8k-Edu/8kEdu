import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import react from '@vitejs/plugin-react'
import { createServer } from 'vite'
import {
  chapterTimelineRange,
  resolveTimelineDuration,
  timelinePlayheadPercent,
  timelineTickPercent,
} from './timeline.js'

const cues = [{ end: 200 }]
const chapters = [{ end: 150 }]

test('duration resolution follows player, transcript, chapter precedence', () => {
  const cases = [
    [300, cues, chapters, 300],
    [300, cues, [], 300],
    [300, [], chapters, 300],
    [300, [], [], 300],
    [null, cues, chapters, 200],
    [null, cues, [], 200],
    [null, [], chapters, 150],
    [null, [], [], null],
  ]
  for (const [playerDuration, cueInput, chapterInput, expected] of cases) {
    assert.equal(resolveTimelineDuration(playerDuration, cueInput, chapterInput), expected)
  }
})

test('invalid player readings retain the artifact fallback', () => {
  for (const playerDuration of [0, -1, NaN, Infinity, -Infinity, undefined]) {
    assert.equal(resolveTimelineDuration(playerDuration, cues, chapters), 200)
  }
})

test('corpus-shaped durations do not depend on concepts', () => {
  assert.equal(resolveTimelineDuration(null, [{ end: 331.84 }], [{ end: 331 }]), 331.84)
  assert.equal(resolveTimelineDuration(null, [{ end: 2111.12 }], []), 2111.12)
  assert.equal(resolveTimelineDuration(null, [{ end: 591.82 }], [{ end: 591 }]), 591.82)
})

test('ticks hide out of range while the playhead clamps', () => {
  assert.equal(timelineTickPercent(0, 300), 0)
  assert.equal(timelineTickPercent(300, 300), 100)
  assert.equal(timelineTickPercent(-1, 300), null)
  assert.equal(timelineTickPercent(301, 300), null)
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
const occurrences = (text, pattern) => (text.match(pattern) ?? []).length

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

test('endpoint ticks render at both boundaries inside the inset plot', () => {
  const markup = renderTimeline({
    duration: 100,
    time: 100,
    concepts: [
      { time: 0, title: 'Start', widget: 'spreadsheet' },
      { time: 100, title: 'End', widget: 'spreadsheet' },
    ],
  })
  assert.doesNotMatch(markup, /NaN|Infinity/)
  assert.equal(occurrences(markup, /data-timeline-tick=/g), 2)
  assert.match(markup, /inset:0 8px/)
  assert.match(markup, /left:0%/)
  assert.match(markup, /left:100%/)
})
