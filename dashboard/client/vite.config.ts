import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // base: './' ensures all asset paths are relative — required for Capacitor (file:// protocol)
  base: './',
  plugins: [
    react(),
  ],
  server: {
    // Dev proxy — only used during `npm run dev`, not in production/mobile build
    proxy: {
      '/api': {
        target: 'http://localhost:4400',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:4400',
        ws: true,
      },
      '/live_video': {
        target: 'http://localhost:4400',
        changeOrigin: true,
      }
    }
  }
})
