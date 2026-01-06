// src/pages/Settings.tsx
// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useState } from 'react';
import { Drawer } from 'vaul';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

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
  const [privacyEnabled, setPrivacyEnabled] = useState(false);

  const [original, setOriginal] = useState({
    autoCloseHours: 12,
    greeting: '',
    defaultAnswer: '',
    autoReplyEnabled: false,
    privacyEnabled: false,
  });

  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    const loadSettings = async () => {
      try {
        setLoading(true);
        setError(null);

        const data = await apiClient.getSettings(instanceId);

        if (isCancelled) return;

        const loadedAutoCloseHours = data.autoclose_hours ?? 12;
        const loadedGreeting = data.autoreply?.greeting ?? '';
        const loadedDefaultAnswer = data.autoreply?.defaultanswer ?? '';
        const loadedAutoReplyEnabled = !!data.autoreply?.enabled;
        const loadedPrivacyEnabled = !!data.privacymodeenabled;

        setAutoCloseHours(loadedAutoCloseHours);
        setGreeting(loadedGreeting);
        setDefaultAnswer(loadedDefaultAnswer);
        setAutoReplyEnabled(loadedAutoReplyEnabled);
        setPrivacyEnabled(loadedPrivacyEnabled);

        setOriginal({
          autoCloseHours: loadedAutoCloseHours,
          greeting: loadedGreeting,
          defaultAnswer: loadedDefaultAnswer,
          autoReplyEnabled: loadedAutoReplyEnabled,
          privacyEnabled: loadedPrivacyEnabled,
        });

        setDirty(false);
      } catch (err: any) {
        if (isCancelled) return;
        setError(err.message);
        // eslint-disable-next-line no-console
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

  const resetToOriginal = () => {
    setAutoCloseHours(original.autoCloseHours);
    setGreeting(original.greeting);
    setDefaultAnswer(original.defaultAnswer);
    setAutoReplyEnabled(original.autoReplyEnabled);
    setPrivacyEnabled(original.privacyEnabled);
    setDirty(false);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      await apiClient.updateSettings(instanceId, {
        autoclose_hours: autoCloseHours,
        autoreply: {
          enabled: autoReplyEnabled,
          greeting: greeting || null,
          defaultanswer: defaultAnswer || null,
        },
        privacymodeenabled: privacyEnabled,
      });

      setOriginal({
        autoCloseHours,
        greeting,
        defaultAnswer,
        autoReplyEnabled,
        privacyEnabled,
      });

      setSuccess(t('settings.save_success'));
      setDirty(false);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(`${t('settings.error_prefix')} ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }} />
          <div style={{ paddingTop: 8 }}>{t('settings.loading')}</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px', paddingBottom: 72 }}>
      <form onSubmit={handleSave}>
        <div className="card">
          <h2 style={{ margin: 0 }}>⚙️ {t('settings.title')}</h2>
        </div>

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
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>👋 {t('settings.greeting_title')}</h3>

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
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>💬 {t('settings.autoreply_title')}</h3>

          <div
            className="form-group"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
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
              <span>{autoReplyEnabled ? t('settings.toggle_on') : t('settings.toggle_off')}</span>
            </label>
          </div>

          <div className="form-group" style={{ marginTop: 8 }}>
            <label className="form-label">{t('settings.autoreply_default_label')}</label>

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
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>⏰ {t('settings.autoclose_title')}</h3>

          <div className="form-group">
            <label className="form-label">{t('settings.autoclose_label')}</label>

            <input
              className="form-input"
              type="number"
              min={1}
              max={168}
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
                marginTop: 4,
                display: 'block',
              }}
            >
              {t('settings.autoclose_hint')}
            </small>
          </div>
        </div>

        {/* Privacy Mode */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>🔒 {t('settings.privacy_title')}</h3>

          <div
            className="form-group"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
          >
            <div>
              <label className="form-label" style={{ marginBottom: 4 }}>
                {t('settings.privacy_label')}
              </label>
              <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block' }}>
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
              <span>{privacyEnabled ? t('settings.toggle_on') : t('settings.toggle_off')}</span>
            </label>
          </div>
        </div>
      </form>

      {/* Premium Sticky Save Button - Vaul Drawer Style */}
      {dirty && (
        <Drawer.Root
          open={dirty}
          onOpenChange={(isOpen) => {
            if (!isOpen) {
              resetToOriginal();
            }
          }}
          modal={true}
          dismissible={true}
        >
          <Drawer.Portal>
            <Drawer.Content
              style={{
                position: 'fixed',
                bottom: 0,
                left: 0,
                right: 0,
                zIndex: 10000,
                outline: 'none',
                pointerEvents: 'auto',
              }}
            >
              <div
                style={{
                  background:
                    'linear-gradient(180deg, rgba(var(--tg-theme-bg-color-rgb, 255, 255, 255), 0) 0%, rgba(var(--tg-theme-bg-color-rgb, 255, 255, 255), 0.8) 20%, var(--tg-theme-bg-color, #fff) 40%)',
                  backdropFilter: 'blur(12px)',
                  WebkitBackdropFilter: 'blur(12px)',
                  paddingTop: 24,
                  paddingBottom: 16,
                  paddingLeft: 16,
                  paddingRight: 16,
                  borderTop: '1px solid rgba(0, 0, 0, 0.06)',
                  boxShadow: '0 -8px 32px rgba(0, 0, 0, 0.08), 0 -2px 8px rgba(0, 0, 0, 0.04)',
                }}
              >
                <div
                  style={{
                    maxWidth: 480,
                    margin: '0 auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      fontSize: 13,
                      color: 'var(--tg-theme-hint-color, rgba(0, 0, 0, 0.5))',
                      fontWeight: 500,
                      marginBottom: 4,
                    }}
                  >
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: '#ff9500',
                        boxShadow: '0 0 8px rgba(255, 149, 0, 0.5)',
                        animation: 'pulse 2s ease-in-out infinite',
                      }}
                    />
                    <span>Несохраненные изменения</span>
                  </div>

                  <button
                    type="submit"
                    disabled={saving}
                    style={{
                      width: '100%',
                      padding: '16px 24px',
                      fontSize: 16,
                      fontWeight: 600,
                      borderRadius: 14,
                      border: 'none',
                      background: saving
                        ? 'linear-gradient(135deg, rgba(33, 150, 243, 0.6) 0%, rgba(21, 101, 192, 0.6) 100%)'
                        : 'linear-gradient(135deg, #2196F3 0%, #1565C0 100%)',
                      color: '#fff',
                      cursor: saving ? 'not-allowed' : 'pointer',
                      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                      boxShadow: saving
                        ? '0 4px 12px rgba(33, 150, 243, 0.2)'
                        : '0 8px 24px rgba(33, 150, 243, 0.35), 0 2px 8px rgba(33, 150, 243, 0.2)',
                      transform: saving ? 'scale(0.98)' : 'scale(1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 10,
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                    onMouseEnter={(e) => {
                      if (!saving) {
                        e.currentTarget.style.transform = 'scale(1.02) translateY(-2px)';
                        e.currentTarget.style.boxShadow =
                          '0 12px 32px rgba(33, 150, 243, 0.45), 0 4px 12px rgba(33, 150, 243, 0.3)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!saving) {
                        e.currentTarget.style.transform = 'scale(1)';
                        e.currentTarget.style.boxShadow =
                          '0 8px 24px rgba(33, 150, 243, 0.35), 0 2px 8px rgba(33, 150, 243, 0.2)';
                      }
                    }}
                  >
                    {saving ? (
                      <>
                        <svg
                          width="20"
                          height="20"
                          viewBox="0 0 24 24"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                          style={{
                            animation: 'spin 1s linear infinite',
                          }}
                        >
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeDasharray="32 32"
                            opacity="0.3"
                          />
                          <path
                            d="M12 2a10 10 0 0 1 10 10"
                            stroke="currentColor"
                            strokeWidth="3"
                            strokeLinecap="round"
                          />
                        </svg>
                        <span>Сохранение...</span>
                      </>
                    ) : (
                      <>
                        <svg
                          width="20"
                          height="20"
                          viewBox="0 0 24 24"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path
                            d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            fill="none"
                          />
                          <path
                            d="M17 21v-8H7v8M7 3v5h8"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                        <span>{t('settings.save_sticky')}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      )}

      <style>
        {`
          @keyframes pulse {
            0%, 100% {
              opacity: 1;
              transform: scale(1);
            }
            50% {
              opacity: 0.7;
              transform: scale(1.1);
            }
          }

          @keyframes spin {
            from {
              transform: rotate(0deg);
            }
            to {
              transform: rotate(360deg);
            }
          }
        `}
      </style>
    </div>
  );
};

export default Settings;