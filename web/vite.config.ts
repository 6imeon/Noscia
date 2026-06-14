/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Listen on all interfaces so the dev server is reachable when containerized
    // (`docker compose up`); harmless for host dev.
    host: true,
    // Dedicated port (5173 is a common default that collides with other dev
    // servers); strictPort fails loudly instead of silently drifting to 5174.
    port: 5180,
    strictPort: true,
    // macOS bind-mounts don't emit reliable fs events; poll inside the container
    // (opt-in via env) so HMR still fires. Host dev keeps native watching.
    watch: process.env.VITE_USE_POLLING ? { usePolling: true } : undefined,
    // Dev proxy: the frontend calls /api/* and Vite forwards to the backend,
    // so the browser stays same-origin (mirrors the deployed reverse proxy).
    // Target is env-driven: host dev → localhost:8000; compose → the `api` service.
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
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
