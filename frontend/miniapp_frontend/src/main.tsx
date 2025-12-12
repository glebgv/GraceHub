// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import './App.css';
import './i18n'; // <-- ДО всего, что использует переводы

// Telegram WebApp SDK уже подключен в index.html через
// <script src="https://telegram.org/js/telegram-web-app.js"></script>
// Здесь читаем initData и query‑параметры и пробрасываем их в App.

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData?: string;
        initDataUnsafe?: {
          user?: {
            id?: number;
            [key: string]: any;
          };
          [key: string]: any;
        };
        ready?: () => void;
        close?: () => void;
        [key: string]: any;
      };
    };
  }
}

const WebApp =
  (typeof window !== 'undefined' && window.Telegram?.WebApp) || null;

if (!WebApp) {
  console.log('[main] WebApp is NOT available on window.Telegram.WebApp');
} else {
  console.log('[main] WebApp detected', {
    initDataPreview: WebApp.initData?.slice(0, 80),
    user: WebApp.initDataUnsafe?.user,
  });
}

// Читаем query‑параметры из URL (используется, когда мастер‑бот присылает индивидуальную ссылку)
const urlParams = new URLSearchParams(window.location.search);
// backend ждёт snake_case, но в React-пропсы кладём как camelCase
const instanceIdFromUrl = urlParams.get('instance_id');
const adminIdFromUrl = urlParams.get('admin_id');

// initData и initDataUnsafe приходят от Telegram WebApp SDK
const initDataRaw: string | null = WebApp?.initData ?? null;
const initDataUnsafe: any = WebApp?.initDataUnsafe ?? null;
const currentUserId: number | null = initDataUnsafe?.user?.id ?? null;

console.log('[main] startup params', {
  search: window.location.search,
  instanceIdFromUrl,
  adminIdFromUrl,
  currentUserId,
  hasInitData: !!initDataRaw,
});

if (WebApp) {
  try {
    WebApp.ready?.();
    console.log('[main] WebApp.ready() called');
  } catch (e) {
    console.warn('Telegram WebApp.ready() error:', e);
  }
}

// Хелпер для закрытия Mini App, который можно прокидывать в App как проп
export const closeMiniApp = () => {
  try {
    if (WebApp?.close) {
      WebApp.close();
      console.log('[main] WebApp.close() called');
    } else {
      console.log('[main] WebApp.close() is not available');
    }
  } catch (e) {
    console.warn('Telegram WebApp.close() error:', e);
  }
};

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App
      instanceIdFromUrl={instanceIdFromUrl}
      adminIdFromUrl={adminIdFromUrl}
      currentUserId={currentUserId}
      initDataRaw={initDataRaw}
      // Можно дальше пробросить этот колбэк и вызвать его в handleLogout
      closeMiniApp={closeMiniApp}
    />
  </React.StrictMode>,
);

