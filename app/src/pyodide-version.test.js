import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

test('Pyodide loader, CDN, and vendor versions stay aligned', async () => {
  const [packageSource, widgetsSource, vendorSource] = await Promise.all([
    readFile(new URL('../package.json', import.meta.url), 'utf8'),
    readFile(new URL('./widgets.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../../scripts/vendor-pyodide.sh', import.meta.url), 'utf8'),
  ])
  const version = JSON.parse(packageSource).dependencies.pyodide

  assert.match(version, /^\d+\.\d+\.\d+$/, 'package.json must pin an exact Pyodide version')
  assert.ok(widgetsSource.includes(`v${version}/full/`), 'Pyodide CDN version must match package.json')
  assert.match(vendorSource, new RegExp(`VERSION="${version.replaceAll('.', '\\.')}"`), 'Pyodide vendor version must match package.json')
})
