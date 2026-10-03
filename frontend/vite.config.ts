import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API (uvicorn eldercare.api.server) runs on :8000; proxying keeps the session
// cookie, MJPEG streams and the event WebSocket same-origin.
const apiTarget = process.env.ELDERCARE_API_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true, ws: true },
    },
  },
})
