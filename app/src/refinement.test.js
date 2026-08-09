import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildRefinementRequest, buildRefinementSource } from './refinement.js'

test('refinement source overlays the widget live state', () => {
  const notebook = buildRefinementSource({
    widget: 'notebook', params: { cells: ['print("old")'], sliders: [{ name: 'n', value: 1 }] },
  }, { cells: ['print("edited")'], sliders: [{ name: 'n', value: 4 }] })
  assert.deepEqual(notebook.params.cells, ['print("edited")'])
  assert.equal(notebook.params.sliders[0].value, 4)

  const spreadsheet = buildRefinementSource({
    widget: 'spreadsheet', params: { cells: [['Name', 'Score'], ['Ada', '1']] },
  }, { cells: [['Name', 'Score'], ['Ada', '9']] })
  assert.equal(spreadsheet.params.cells[1][1], '9')
})

test('source bounding keeps complete notebook cells and spreadsheet rows', () => {
  const long = 'x'.repeat(7000)
  const notebook = buildRefinementSource({ widget: 'notebook', params: { cells: [long, long] } })
  assert.deepEqual(notebook.params.cells, [long])

  const row = Array.from({ length: 3 }, () => 'x'.repeat(2500))
  const spreadsheet = buildRefinementSource({ widget: 'spreadsheet', params: { cells: [row, row] } })
  assert.deepEqual(spreadsheet.params.cells, [row])
})

test('refinement keeps saved and pipeline replacement identities', () => {
  const saved = buildRefinementRequest({ spec: { time: 3, params: {} }, instruction: 'edit', text: '', video: 'v', cloud: false, replaces: 'saved-id', replacesKey: 'ignored' })
  const pipeline = buildRefinementRequest({ spec: { time: 3, params: {} }, instruction: 'edit', text: '', video: 'v', cloud: false, replaces: '', replacesKey: 'softmax@3' })
  assert.equal(saved.replaces, 'saved-id')
  assert.equal(pipeline.replaces_key, 'softmax@3')
})
