import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'
import { existsSync, readdirSync, rmSync } from 'node:fs'
import path from 'node:path'

// Branch-aware host: dev branch → http://dev.localhost:5174 , everything else → http://localhost:5173
// (*.localhost resolves to loopback in modern browsers — no /etc/hosts edit needed)
const branch = (() => {
  try { return execSync('git rev-parse --abbrev-ref HEAD').toString().trim() } catch { return 'main' }
})()
const isDev = branch === 'dev'
const HOST = isDev ? 'dev.localhost' : 'localhost'
const PORT = isDev ? 5174 : 5173

// print the branded URL once the server is listening
const banner = () => ({
  name: 'branch-host-banner',
  configureServer(server) {
    const orig = server.printUrls.bind(server)
    server.printUrls = () => {
      console.log(`\n  8kedu [${branch}]  ➜  http://${HOST}:${PORT}/\n`)
      orig()
    }
  },
})

// publicDir is data/, where serve.py caches frames fetched from a private bucket — serving
// that tree wholesale would republish them and bake them into dist/. Anchored to
// `<videoId>/(frames|crops)/…` so a future top-level route named /frames/… would not
// silently 404.
const PRIVATE_DATA = /^\/[^/]+\/(frames|crops)\//
const hideCachedFrames = () => {
  let outDir
  return {
    name: 'hide-cached-frames',
    configResolved(c) { outDir = path.resolve(c.root, c.build.outDir) },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (PRIVATE_DATA.test((req.url || '').split('?')[0])) {
          res.statusCode = 404
          res.end()
          return
        }
        next()
      })
    },
    // publicDir is copied at the very end of the build, so buildEnd is too early.
    closeBundle() {
      if (!outDir || !existsSync(outDir)) return
      for (const entry of readdirSync(outDir, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue
        for (const dir of ['frames', 'crops']) {
          rmSync(path.join(outDir, entry.name, dir), { recursive: true, force: true })
        }
      }
    },
  }
}

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/8kedu/' : '/', // prod: served under dev.perspectivity.co/8kedu
  plugins: [react(), banner(), hideCachedFrames()],
  publicDir: '../data', // serves concepts.json + the vendored pyodide straight from the pipeline
  server: {
    host: true,                                    // bind loopback; browser reaches via *.localhost
    port: PORT,
    strictPort: true,
    allowedHosts: ['localhost', 'dev.localhost', '.localhost'],
    proxy: {
      '/api': 'http://127.0.0.1:8756',             // ask endpoint (serve.py)
      '/agent': 'http://127.0.0.1:8787',           // agent dashboard API (agent/api.py)
      '/pub': 'http://127.0.0.1:8787',             // community remix feed (agent/api.py)
    },
  },
}))
