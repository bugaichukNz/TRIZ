import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat': { target: API_TARGET, changeOrigin: true },
      '/solve': { target: API_TARGET, changeOrigin: true },
      '/sessions': { target: API_TARGET, changeOrigin: true },
      '/health': { target: API_TARGET, changeOrigin: true },
      '/state': { target: API_TARGET, changeOrigin: true },
      '/auth': { target: API_TARGET, changeOrigin: true },
    },
  },
})
