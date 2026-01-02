import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Загружаем .env из ~/GraceHub/ (родительская папка)
  const envDir = path.resolve(__dirname, '../')
  const env = loadEnv(mode, envDir, '') // '' = все переменные без VITE_

  const domain = env.WEBHOOK_DOMAIN || 'localhost'

  return {
    plugins: [react()],
    envDir,

    // ВАЖНО: miniapp dev смонтирован под /app/
    // Это заставит Vite отдавать client/assets с префиксом /app/ вместо /. [web:109]
    base: '/app/',

    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,

      // allowedHosts — чтобы Vite отвечал на запросы с Host: gracehub.ru [web:23]
      allowedHosts: [domain, `www.${domain}`, 'localhost'],

      // ВАЖНО: HMR по wss через домен/443 (nginx TLS), иначе клиент будет пытаться ходить не туда. [web:23][web:24]
      hmr: {
        protocol: 'wss',
        host: domain,
        clientPort: 443,

        // Если после base всё равно будет странный путь, можно раскомментировать:
        // path: '/app/',
      },

      proxy: {
        '/api': {
          target: 'http://localhost:8001',
          changeOrigin: true,
        },
      },
    },

    define: {
      // Делаем доступными глобально везде
      'process.env.WEBHOOK_DOMAIN': JSON.stringify(domain),
      'import.meta.env.WEBHOOK_DOMAIN': JSON.stringify(domain),
    },

    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})

