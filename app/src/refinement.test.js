import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildRefinementRequest, buildRefinementSource, nextRefinementRevision, widgetInstanceKey } from './refinement.js'

test('refinement source overlays the widget live state', () => {
  const notebook = buildRefinementSource({
    widget: 'notebook', params: { cells: ['print("old")', 'print("saved")'], sliders: [{ name: 'n', value: 1 }] },
  }, { cells: ['print("edited")', 'print("kept")'], sliders: [{ name: 'n', value: 4 }] })
  assert.deepEqual(notebook.params.cells, ['print("edited")', 'print("kept")'])
  assert.equal(notebook.params.sliders[0].value, 4)

  const spreadsheet = buildRefinementSource({
    widget: 'spreadsheet', params: { cells: [['Name', 'Score'], ['Ada', '1'], ['Lin', '2']] },
  }, { cells: [['Name', 'Score'], ['Ada', '9'], ['Lin', '3']] })
  assert.equal(spreadsheet.params.cells[1][1], '9')
  assert.equal(spreadsheet.params.cells[2][1], '3')
})

test('refinement source keeps complete notebook cells and spreadsheet rows', () => {
  const long = 'x'.repeat(7000)
  const notebook = buildRefinementSource({ widget: 'notebook', params: { cells: [long, long] } })
  assert.deepEqual(notebook.params.cells, [long, long])

  const row = Array.from({ length: 3 }, () => 'x'.repeat(2500))
  const spreadsheet = buildRefinementSource({ widget: 'spreadsheet', params: { cells: [row, row] } })
  assert.deepEqual(spreadsheet.params.cells, [row, row])
})

test('successful refinements advance the same-widget instance key', () => {
  const widget = { time: 12, widget: 'notebook' }
  const revision = 4
  const successRevision = nextRefinementRevision(revision, 'success')
  assert.equal(successRevision, 5)
  assert.notEqual(widgetInstanceKey(widget, revision), widgetInstanceKey(widget, successRevision))
  assert.equal(nextRefinementRevision(revision, 'error'), revision)
  assert.equal(nextRefinementRevision(revision, 'answer'), revision)
  assert.equal(widgetInstanceKey(widget, revision), widgetInstanceKey(widget, nextRefinementRevision(revision, 'error')))
})

test('refinement keeps saved and pipeline replacement identities', () => {
  const saved = buildRefinementRequest({ spec: { time: 3, params: {} }, instruction: 'edit', text: '', video: 'v', cloud: false, replaces: 'saved-id', replacesKey: 'ignored' })
  const pipeline = buildRefinementRequest({ spec: { time: 3, params: {} }, instruction: 'edit', text: '', video: 'v', cloud: false, replaces: '', replacesKey: 'softmax@3' })
  assert.equal(saved.replaces, 'saved-id')
  assert.equal(pipeline.replaces_key, 'softmax@3')
})
