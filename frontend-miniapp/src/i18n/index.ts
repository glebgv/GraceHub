// src/i18n/index.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import ru from './locales/ru.json';
import en from './locales/en.json';
import es from './locales/es.json';
import hi from './locales/hi.json';
import zh from './locales/zh.json';

export const DEFAULT_LANG = 'ru';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
      es: { translation: es },
      hi: { translation: hi },
      zh: { translation: zh }
    },
    lng: DEFAULT_LANG,
    fallbackLng: 'en',
    supportedLngs: ['ru', 'en', 'es', 'hi', 'zh'],
    interpolation: {
      escapeValue: false
    },
    react: {
      useSuspense: false,
      bindI18n: 'languageChanged loaded',
      bindI18nStore: 'added removed',
      transEmptyNodeValue: '',
      transSupportBasicHtmlNodes: true,
      transKeepBasicHtmlNodesFor: ['br', 'strong', 'i', 'p']
    }
  });

export default i18n;
