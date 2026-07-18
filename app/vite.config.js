import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  publicDir: '../data', // serves concepts.json + frames/ straight from the pipeline
  server: {
    proxy: { '/api': 'http://127.0.0.1:8756' }, // ask endpoint (serve.py)
  },
})
