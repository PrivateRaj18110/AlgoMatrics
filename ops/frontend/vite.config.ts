import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  // The ops dashboard is served under /ops by the AlgoMatrics frontend nginx.
  base: '/ops/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Manual chunking keeps the heavy data-grid / charting libraries out of the
    // main bundle so the initial paint stays fast on laptops and older iPads.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('ag-grid')) return 'vendor-grid'
          if (id.includes('recharts') || id.includes('d3-') || id.includes('victory'))
            return 'vendor-charts'
          if (id.includes('react-router') || id.includes('react-grid-layout')) return 'vendor-router'
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    host: true,
    // Mirrors the production nginx route: /ops/api → ops backend (:8001 in dev).
    proxy: {
      '/ops/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/ops/, ''),
      },
    },
  },
})
