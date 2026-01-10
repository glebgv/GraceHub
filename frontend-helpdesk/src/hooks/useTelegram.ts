import { useEffect, useState } from 'react';
import type { TelegramWebApp, TelegramUser } from '../types/telegram';

export function useTelegram() {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null);
  const [user, setUser] = useState<TelegramUser | null>(null);
  const [initData, setInitData] = useState<string>('');
  const [isReady, setIsReady] = useState(false);
  const [colorScheme, setColorScheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    
    if (tg) {
      tg.ready();
      tg.expand();
      
      setWebApp(tg);
      setUser(tg.initDataUnsafe.user || null);
      setInitData(tg.initData);
      setColorScheme(tg.colorScheme);
      setIsReady(true);

      // Apply theme
      if (tg.colorScheme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
    } else {
      // For development without Telegram
      setIsReady(true);
      setUser({
        id: 123456789,
        is_bot: false,
        first_name: 'Test',
        username: 'testuser'
      });
    }
  }, []);

  return {
    webApp,
    user,
    initData,
    isReady,
    colorScheme,
    showAlert: (message: string) => webApp?.showAlert(message),
    showConfirm: (message: string) => webApp?.showConfirm(message) || Promise.resolve(false),
    close: () => webApp?.close(),
    haptic: (type: 'light' | 'medium' | 'heavy' = 'light') => {
      webApp?.HapticFeedback?.impactOccurred(type);
    }
  };
}
