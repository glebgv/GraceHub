import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  // УБРАТЬ base: '/app/' - теперь корень
  // base: '/app/',

  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,

    hmr: {
      protocol: 'wss',
      host: 'app.gracehub.ru',
      clientPort: 443,
    },

    proxy: {
      '/api': {
        target: 'http://api:8001',
        changeOrigin: true,
      },
    },

    watch: {
      usePolling: true,
      interval: 1000,
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    cssMinify: 'esbuild',
  },
})

