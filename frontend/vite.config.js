import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // lets the frontend call /api/... in dev without CORS headaches
      '/api': 'http://localhost:8000',
    },
  },
})
