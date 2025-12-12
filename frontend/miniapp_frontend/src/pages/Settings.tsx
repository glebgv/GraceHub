import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

interface SettingsProps {
  instanceId: string;
}

const Settings: React.FC<SettingsProps> = ({ instanceId }) => {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [autoCloseHours, setAutoCloseHours] = useState(12);
  const [greeting, setGreeting] = useState('');
  const [defaultAnswer, setDefaultAnswer] = useState('');

  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [openChatEnabled, setOpenChatEnabled] = useState(false);
  const [privacyEnabled, setPrivacyEnabled] = useState(false);

  const [language, setLanguage] = useState<LangCode>('ru');

  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    const loadSettings = async () => {
      try {
        setLoading(true);
        setError(null);

        const data = await apiClient.getSettings(instanceId);

        if (isCancelled) return;

        setAutoCloseHours(data.autoclose_hours ?? 12);
        setGreeting(data.autoreply?.greeting ?? '');
        setDefaultAnswer(data.autoreply?.defaultanswer ?? '');
        setAutoReplyEnabled(!!data.autoreply?.enabled);
        setOpenChatEnabled(!!data.openchatenabled);
        setPrivacyEnabled(!!data.privacymodeenabled);

        const lang: LangCode = (data.language as LangCode) || 'ru';
        setLanguage(lang);
        // язык переключается централизованно в App, здесь не трогаем i18n

        setDirty(false);
      } catch (err: any) {
        if (isCancelled) return;
        setError(err.message);
        console.error('Ошибка загрузки настроек:', err);
      } finally {
        if (isCancelled) return;
        setLoading(false);
      }
    };

    loadSettings();

    return () => {
      isCancelled = true;
    };
  }, [instanceId]);

  const handleLanguageSelect = (lang: LangCode) => {
    setLanguage(lang);
    // не меняем i18n напрямую, дождёмся сохранения и повторной загрузки настроек в App
    setDirty(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError(null);
      setSuccess(null);

      await apiClient.updateSettings(instanceId, {
        autoclose_hours: autoCloseHours,
        autoreply: {
          enabled: autoReplyEnabled,
          greeting: greeting || null,
          defaultanswer: defaultAnswer || null,
        },
        openchatenabled: openChatEnabled,
        privacymodeenabled: privacyEnabled,
        language: language,
      });

      setSuccess(t('settings.save_success'));
      setDirty(false);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(`${t('settings.error_prefix')} ${err.message}`);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }}></div>
          <p>{t('settings.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px', paddingBottom: '72px' }}>
      <form onSubmit={handleSave}>
        <div className="card">
          <h2 style={{ margin: 0 }}>⚙️ {t('settings.title')}</h2>
        </div>

        {/* Липкое сообщение об успехе */}
        {success && (
          <div
            className="card"
            style={{
              marginTop: 8,
              marginBottom: 8,
              position: 'sticky',
              top: 8,
              zIndex: 51,
              background: '#2196F3',
              borderColor: '#2196F3',
            }}
          >
            <p style={{ margin: 0, color: '#FFFFFF' }}>{success}</p>
          </div>
        )}

        {/* Липкая кнопка сохранения */}
        {dirty && (
          <div
            className="card"
            style={{
              marginTop: 8,
              marginBottom: 8,
              position: 'sticky',
              top: 8,
              zIndex: 50,
            }}
          >
            <button className="btn btn-primary btn-block" type="submit">
              💾 {t('settings.save_sticky')}
            </button>
          </div>
        )}

        {error && (
          <div
            className="card"
            style={{
              background: 'rgba(255, 51, 51, 0.1)',
              borderColor: 'rgba(255, 51, 51, 0.3)',
            }}
          >
            <p style={{ margin: 0, color: 'var(--tg-color-text)' }}>{error}</p>
          </div>
        )}

        {/* Приветствие */}
        <div className="card" style={{ marginTop: '12px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px' }}>
            👋 {t('settings.greeting_title')}
          </h3>
          <div className="form-group">
            <label className="form-label">{t('settings.greeting_label')}</label>
            <textarea
              className="form-textarea"
              value={greeting}
              onChange={(e) => {
                setGreeting(e.target.value);
                setDirty(true);
              }}
              placeholder={t('settings.greeting_placeholder')}
              rows={3}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '8px',
                border: '1px solid var(--tg-color-hint)',
                fontFamily: 'inherit',
              }}
            />
          </div>
        </div>

        {/* Автоответ */}
        <div className="card" style={{ marginTop: '12px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px' }}>
            💬 {t('settings.autoreply_title')}
          </h3>
          <div
            className="form-group"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <label className="form-label" style={{ marginBottom: 0 }}>
              {t('settings.autoreply_enabled_label')}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={autoReplyEnabled}
                onChange={(e) => {
                  setAutoReplyEnabled(e.target.checked);
                  setDirty(true);
                }}
              />
              <span>
                {autoReplyEnabled
                  ? t('settings.toggle_on')
                  : t('settings.toggle_off')}
              </span>
            </label>
          </div>
          <div className="form-group" style={{ marginTop: '8px' }}>
            <label className="form-label">
              {t('settings.autoreply_default_label')}
            </label>
            <textarea
              className="form-textarea"
              value={defaultAnswer}
              onChange={(e) => {
                setDefaultAnswer(e.target.value);
                setDirty(true);
              }}
              placeholder={t('settings.autoreply_default_placeholder')}
              rows={3}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '8px',
                border: '1px solid var(--tg-color-hint)',
                fontFamily: 'inherit',
              }}
            />
          </div>
        </div>

        {/* Автоматическое закрытие */}
        <div className="card" style={{ marginTop: '12px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px' }}>
            ⏰ {t('settings.autoclose_title')}
          </h3>
          <div className="form-group">
            <label className="form-label">
              {t('settings.autoclose_label')}
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="168"
              value={autoCloseHours}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                setAutoCloseHours(Number.isNaN(v) ? 12 : v);
                setDirty(true);
              }}
            />
            <small
              style={{
                color: 'var(--tg-color-text-secondary)',
                marginTop: '4px',
                display: 'block',
              }}
            >
              {t('settings.autoclose_hint')}
            </small>
          </div>
        </div>

        {/* Privacy Mode */}
        <div className="card" style={{ marginTop: '12px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px' }}>
            🔒 {t('settings.privacy_title')}
          </h3>
          <div
            className="form-group"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div>
              <label className="form-label" style={{ marginBottom: '4px' }}>
                {t('settings.privacy_label')}
              </label>
              <small
                style={{
                  color: 'var(--tg-color-text-secondary)',
                  display: 'block',
                }}
              >
                {t('settings.privacy_hint')}
              </small>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={privacyEnabled}
                onChange={(e) => {
                  setPrivacyEnabled(e.target.checked);
                  setDirty(true);
                }}
              />
              <span>
                {privacyEnabled
                  ? t('settings.toggle_on')
                  : t('settings.toggle_off')}
              </span>
            </label>
          </div>
        </div>

        {/* Язык интерфейса */}
        <div className="card" style={{ marginTop: '12px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px' }}>
            🌐 {t('settings.language_title')}
          </h3>
          <div className="form-group">
            <label className="form-label">
              {t('settings.language_label')}
            </label>
            <select
              className="form-select"
              value={language}
              onChange={(e) => handleLanguageSelect(e.target.value as LangCode)}
            >
              <option value="ru">{t('settings.language_ru')}</option>
              <option value="en">{t('settings.language_en')}</option>
              <option value="es">{t('settings.language_es')}</option>
              <option value="hi">{t('settings.language_hi')}</option>
              <option value="zh">{t('settings.language_zh')}</option>
            </select>
            <small
              style={{
                color: 'var(--tg-color-text-secondary)',
                marginTop: '4px',
                display: 'block',
              }}
            >
              {t('settings.language_hint')}
            </small>
          </div>
        </div>
      </form>
    </div>
  );
};

export default Settings;
