#!/bin/bash

# Создаем директории если они не существуют
mkdir -p src/styles

# Создаем файлы

cat <<'EOF' > src/App.tsx
import { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useTelegram } from './hooks/useTelegram';
import HelpdeskAPI from './api/helpdesk';

// Pages
import LoadingPage from './pages/LoadingPage';
import NotFoundPage from './pages/NotFoundPage';
import DashboardPage from './pages/DashboardPage';
import TicketsPage from './pages/TicketsPage';
import TicketDetailsPage from './pages/TicketDetailsPage';
import OperatorsPage from './pages/OperatorsPage';

export default function App() {
  const { user, initData, isReady, colorScheme } = useTelegram();
  const [api, setApi] = useState<HelpdeskAPI | null>(null);
  const [instanceId, setInstanceId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;

    // Get instance ID from URL
    const params = new URLSearchParams(window.location.search);
    const instance = params.get('instance');

    if (!instance) {
      setError('Instance ID не найден в URL');
      return;
    }

    setInstanceId(instance);
    
    // Initialize API
    try {
      const helpdeskApi = new HelpdeskAPI(instance, initData || '');
      setApi(helpdeskApi);
    } catch (err) {
      setError('Ошибка инициализации API');
      console.error('API initialization error:', err);
    }
  }, [isReady, initData]);

  if (!isReady) {
    return <LoadingPage />;
  }

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center bg-red-50 dark:bg-red-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-800 dark:text-red-200 mb-2">Ошибка</h1>
          <p className="text-red-700 dark:text-red-300">{error}</p>
        </div>
      </div>
    );
  }

  if (!api || !user) {
    return <LoadingPage />;
  }

  return (
    <Router basename="/helpdesk">
      <div className={colorScheme === 'dark' ? 'dark' : ''}>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage api={api} />} />
            <Route path="/tickets" element={<TicketsPage api={api} />} />
            <Route path="/tickets/:ticketId" element={<TicketDetailsPage api={api} />} />
            <Route path="/operators" element={<OperatorsPage api={api} />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}
EOF

cat <<'EOF' > src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './styles/globals.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
EOF

cat <<'EOF' > src/App.css
/* Empty, styles handled by Tailwind */
EOF

cat <<'EOF' > src/vite-env.d.ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
EOF

cat <<'EOF' > src/styles/globals.css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    scroll-behavior: smooth;
  }

  body {
    @apply antialiased;
  }

  /* Custom scrollbar */
  ::-webkit-scrollbar {
    @apply w-2 h-2;
  }

  ::-webkit-scrollbar-track {
    @apply bg-gray-100 dark:bg-gray-800;
  }

  ::-webkit-scrollbar-thumb {
    @apply bg-gray-400 dark:bg-gray-600 rounded-lg hover:bg-gray-500 dark:hover:bg-gray-500;
  }
}

@layer components {
  .container-safe {
    @apply max-w-2xl mx-auto px-4;
  }

  .card {
    @apply bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4;
  }

  .input-field {
    @apply w-full px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-20;
  }

  .button-primary {
    @apply px-4 py-2 rounded-lg bg-blue-500 hover:bg-blue-600 text-white font-medium transition disabled:opacity-50 disabled:cursor-not-allowed;
  }

  .button-secondary {
    @apply px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 font-medium transition;
  }

  .badge-base {
    @apply inline-block px-2.5 py-0.5 rounded-full text-xs font-medium;
  }
}
EOF

cat <<'EOF' > src/styles/tailwind.css
@tailwind base;
@tailwind components;
@tailwind utilities;
EOF

cat <<'EOF' > tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Custom colors if needed
      },
      animation: {
        // Custom animations if needed
      },
    },
  },
  plugins: [],
  darkMode: 'class',
}
EOF

cat <<'EOF' > postcss.config.js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF

cat <<'EOF' > .env.example
VITE_API_BASE_URL=http://localhost:8000/api
EOF

cat <<'EOF' > .gitignore
node_modules/
dist/
.env
.env.local
.env.*.local
*.log
.DS_Store
.vscode/
.idea/
*.swp
*.swo
*~
EOF

cat <<'EOF' > index.html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/helpdesk/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="GraceHub Helpdesk Mini App" />
    <meta name="theme-color" content="#3b82f6" />
    
    <!-- Telegram Mini App SDK -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    
    <title>Helpdesk</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF

cat <<'EOF' > tsconfig.node.json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
EOF

echo "Все файлы созданы успешно."
