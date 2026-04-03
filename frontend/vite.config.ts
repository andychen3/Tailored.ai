import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiProxyTarget = 'http://127.0.0.1:8000'
const largeUploadTimeoutMs = 30 * 60 * 1000

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    clearMocks: true,
  },
  server: {
    proxy: {
      '/chat': {
        target: apiProxyTarget,
        changeOrigin: true,
        timeout: largeUploadTimeoutMs,
        proxyTimeout: largeUploadTimeoutMs,
      },
      '/health': {
        target: apiProxyTarget,
        changeOrigin: true,
        timeout: largeUploadTimeoutMs,
        proxyTimeout: largeUploadTimeoutMs,
      },
      '/ingest': {
        target: apiProxyTarget,
        changeOrigin: true,
        timeout: largeUploadTimeoutMs,
        proxyTimeout: largeUploadTimeoutMs,
      },
      '/sources': {
        target: apiProxyTarget,
        changeOrigin: true,
        timeout: largeUploadTimeoutMs,
        proxyTimeout: largeUploadTimeoutMs,
      },
      '/integrations': {
        target: apiProxyTarget,
        changeOrigin: true,
        timeout: largeUploadTimeoutMs,
        proxyTimeout: largeUploadTimeoutMs,
      },
    },
  },
})
