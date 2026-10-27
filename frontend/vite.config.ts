import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: { rollupOptions: { input: { landing: resolve(__dirname, 'index.html'), app: resolve(__dirname, 'app/index.html') } } },
  server: { proxy: { '/api': 'http://localhost:8000', '/media': 'http://localhost:8000' } },
})
