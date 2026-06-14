/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dedicated port (5173 is a common default that collides with other dev
    // servers); strictPort fails loudly instead of silently drifting to 5174.
    port: 5180,
    strictPort: true,
    // Dev proxy: the frontend calls /api/* and Vite forwards to the backend,
    // so the browser stays same-origin (mirrors the deployed reverse proxy).
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
