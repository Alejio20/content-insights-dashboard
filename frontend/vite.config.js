/**
 * @file Vite build and dev-server configuration.
 * Enables the React plugin for automatic JSX transform and configures
 * Vitest to use jsdom with global test helpers for component testing.
 */

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
