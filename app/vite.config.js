import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'

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

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/8kedu/' : '/', // prod: served under dev.perspectivity.co/8kedu
  plugins: [react(), banner()],
  publicDir: '../data', // serves concepts.json + frames/ straight from the pipeline
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
