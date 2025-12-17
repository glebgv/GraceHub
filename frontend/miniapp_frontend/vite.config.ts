import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Загружаем .env из ~/GraceHub/ (родительская папка)
  const envDir = path.resolve(__dirname, '../')
  const env = loadEnv(mode, envDir, '') // '' = все переменные без VITE_

  return {
    plugins: [react()],
    envDir,
    server: {
      host: '0.0.0.0',
      port: 5173,
      allowedHosts: [env.WEBHOOK_DOMAIN, `www.${env.WEBHOOK_DOMAIN}`, 'localhost'],
      proxy: {
        '/api': {
          target: 'http://localhost:8001',
          changeOrigin: true,
        },
      },
    },
    define: {
      // Делаем доступными глобально везде
      'process.env.WEBHOOK_DOMAIN': JSON.stringify(env.WEBHOOK_DOMAIN),
      'import.meta.env.WEBHOOK_DOMAIN': JSON.stringify(env.WEBHOOK_DOMAIN),
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})

