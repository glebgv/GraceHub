// src/pages/FirstLaunch.tsx
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../api/client';
import AddBotModal from '../components/AddBotModal';
import logo from '../assets/logo.png';

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

interface FirstLaunchProps {
  onAddBotClick: (token: string) => Promise<void> | void;
  instanceId?: string | null;
}

const FirstLaunch: React.FC<FirstLaunchProps> = ({
  onAddBotClick,
  instanceId,
}) => {
  const { t, i18n } = useTranslation();

  const initialLang = (i18n.language as LangCode) || 'ru';
  const [language, setLanguage] = useState<LangCode>(initialLang);
  const [saving, setSaving] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  const saveLanguage = async (lang: LangCode) => {
    if (!instanceId) return;
    try {
      setSaving(true);
      await apiClient.updateSettings(instanceId, {
        language: lang,
      });
    } catch (err) {
      console.error('[FirstLaunch] Failed to update language', err);
    } finally {
      setSaving(false);
    }
  };

  const handleLanguageClick = (lang: LangCode) => {
    setLanguage(lang);          // мгновенно подсвечиваем кнопку
    i18n.changeLanguage(lang);  // меняем язык в UI
    void saveLanguage(lang);    // асинхронно сохраняем на бэке
  };

  const handleSubmitToken = async (token: string) => {
    await onAddBotClick(token);
  };

  const languageOptions: { code: LangCode; label: string }[] = [
    { code: 'ru', label: 'Русский' },
    { code: 'en', label: 'English' },
    { code: 'es', label: 'Español' },
    { code: 'hi', label: 'हिन्दी' },
    { code: 'zh', label: '中文' },
  ];

  return (
    <div style={{ padding: 12 }}>
      {/* Заголовок и приветствие */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardbody">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 8,
            }}
          >
            <img
              src={logo}
              alt="GraceHub"
              style={{
                width: 32,
                height: 32,
                borderRadius: 10,
              }}
            />
            <span style={{ fontSize: 22, fontWeight: 600 }}>
              {t('app.title')}
            </span>
          </div>

          <p
            style={{
              margin: 0,
              fontSize: 14,
              color: 'var(--tg-color-text-secondary)',
            }}
          >
            {t('firstLaunch.welcome')}
          </p>

          <p
            style={{
              marginTop: 6,
              marginBottom: 0,
              fontSize: 13,
              color: 'var(--tg-color-text-secondary)',
            }}
          >
            {t('firstLaunch.description')}
          </p>

          {/* Быстрый выбор языка (псевдо-dropdown) */}
          <div style={{ marginTop: 12 }}>
            <label
              className="form-label"
              style={{
                fontSize: 12,
                color: 'var(--tg-color-text-secondary)',
                marginBottom: 6,
                display: 'block',
              }}
            >
              {t('settings.languageLabel')}
            </label>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              {languageOptions.map((item) => {
                const active = language === item.code;
                return (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => handleLanguageClick(item.code)}
                    disabled={saving}
                    style={{
                      padding: '6px 10px',
                      borderRadius: 999,
                      border: active
                        ? '1px solid var(--tg-color-accent)'
                        : '1px solid var(--tg-color-hint)',
                      backgroundColor: active
                        ? 'var(--tg-color-accent)'
                        : 'var(--tg-theme-bg-color, #ffffff)',
                      color: active
                        ? '#ffffff'
                        : 'var(--tg-color-text, #000000)',
                      fontSize: 12,
                      lineHeight: 1.2,
                      minWidth: 64,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
            {saving && (
              <small
                style={{
                  display: 'block',
                  marginTop: 4,
                  fontSize: 11,
                  color: 'var(--tg-color-text-secondary)',
                }}
              >
                {t('firstLaunch.savingLanguage')}
              </small>
            )}
          </div>
        </div>
      </div>

      {/* Основные действия (аналоги меню бота) */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardbody">
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>
            {t('firstLaunch.actionsTitle')}
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
              className="btn btn--primary btn--full-width"
              onClick={() => setShowAddModal(true)}
            >
              ➕ {t('firstLaunch.addBot')}
            </button>
          </div>
        </div>
      </div>

      {/* Подсказка как начать */}
      <div className="card">
        <div className="cardbody">
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>
            {t('firstLaunch.howToStartTitle')}
          </h3>
          <ol
            style={{
              margin: 0,
              paddingLeft: 18,
              fontSize: 14,
              color: 'var(--tg-color-text-secondary)',
            }}
          >
            <li>{t('firstLaunch.step1')}</li>
            <li>{t('firstLaunch.step2')}</li>
            <li>{t('firstLaunch.step3')}</li>
          </ol>
        </div>
      </div>

      {showAddModal && (
        <AddBotModal
          onClose={() => setShowAddModal(false)}
          onSubmitToken={handleSubmitToken}
        />
      )}
    </div>
  );
};

export default FirstLaunch;
