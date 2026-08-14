import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy do /v1 para o backend. Dentro do docker-compose, sobrescreva via
// VITE_PROXY_TARGET=http://backend:8001 (ver docker-compose.yml).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/v1': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
