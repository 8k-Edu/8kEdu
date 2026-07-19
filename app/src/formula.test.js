import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evalFormula } from './formula.js'

const g = (rows) => rows.map(r => r.map(v => ({ value: v, style: {} })))

test('plain number passes through', () => {
  assert.equal(evalFormula('42', g([['42']])), 42)
})
test('non-formula string passes through', () => {
  assert.equal(evalFormula('Jan', g([['Jan']])), 'Jan')
})
test('arithmetic with precedence and parens', () => {
  assert.equal(evalFormula('=2+3*4', g([[]])), 14)
  assert.equal(evalFormula('=(2+3)*4', g([[]])), 20)
  assert.equal(evalFormula('=-5+2', g([[]])), -3)
})
test('cell ref', () => {
  assert.equal(evalFormula('=A1*2', g([[10]])), 20)
})
test('SUM over a range', () => {
  assert.equal(evalFormula('=SUM(A1:A3)', g([[10],[20],[30]])), 60)
})
test('AVERAGE / MIN / MAX / COUNT', () => {
  const grid = g([[10],[20],[30]])
  assert.equal(evalFormula('=AVERAGE(A1:A3)', grid), 20)
  assert.equal(evalFormula('=MIN(A1:A3)', grid), 10)
  assert.equal(evalFormula('=MAX(A1:A3)', grid), 30)
  assert.equal(evalFormula('=COUNT(A1:A3)', grid), 3)
})
test('nested formula reference resolves', () => {
  // A1=5, A2==A1*2, B1==A2+1  → 11
  assert.equal(evalFormula('=A2+1', g([[5, '=A1*2'], ['=A1*2']])), 11)
})
test('bad ref returns #REF!', () => {
  assert.equal(evalFormula('=ZZ99+1', g([[1]])), '#REF!')
})
test('cycle returns #CYCLE', () => {
  // A1==B1, B1==A1
  const grid = g([['=B1', '=A1']])
  assert.equal(evalFormula('=A1', grid), '#CYCLE')
})
test('binary minus and divide', () => {
  assert.equal(evalFormula('=10-3', g([[]])), 7)
  assert.equal(evalFormula('=10/4', g([[]])), 2.5)
})
test('malformed formulas return #REF!', () => {
  assert.equal(evalFormula('=(2+3', g([[]])), '#REF!')
  assert.equal(evalFormula('=2+3)', g([[]])), '#REF!')
  assert.equal(evalFormula('=5%2', g([[]])), '#REF!')
})
test('out-of-bounds column returns #REF! (consistent with out-of-bounds row)', () => {
  assert.equal(evalFormula('=B1+1', g([[1]])), '#REF!')
})
