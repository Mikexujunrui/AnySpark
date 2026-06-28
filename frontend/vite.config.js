import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/d3')) return 'd3'
          if (id.includes('node_modules/leaflet') || id.includes('node_modules/react-leaflet')) return 'leaflet'
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 8190,
    proxy: { '/api': 'http://localhost:8191' }
  }
})
