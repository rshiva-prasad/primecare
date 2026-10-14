import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  // Preview serves on the dev origin (an allowed origin) and inherits the /api proxy above.
  preview: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/types/**', 'src/test/**', 'src/**/*.test.{ts,tsx}'],
      reporter: ['text', 'html'],
      thresholds: {
        lines: 80,
        statements: 80,
        functions: 80,
        branches: 80,
      },
    },
  },
})
