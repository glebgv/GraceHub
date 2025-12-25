// src/pages/FirstLaunch.tsx

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../api/client';
import AddBotModal from '../components/AddBotModal';
import logo from '../assets/logo.png';

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

interface FirstLaunchProps {
  onAddBotClick: (token: string) => Promise<void> | void;
  instanceId?: string | null;

  // NEW (for superadmin without instances)
  isSuperadmin?: boolean;
  onOpenAdmin?: () => void;
}

type OfferState = {
  enabled: boolean;
  url: string;
  accepted: boolean;
  loading: boolean;
  error: string | null;
};

const FirstLaunch: React.FC<FirstLaunchProps> = ({
  onAddBotClick,
  instanceId,
  isSuperadmin,
  onOpenAdmin,
}) => {
  const { t, i18n } = useTranslation();

  const initialLang = (i18n.language as LangCode) || 'ru';
  const [language, setLanguage] = useState<LangCode>(initialLang);
  const [saving, setSaving] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  // --- Offer gate state ---
  const [offer, setOffer] = useState<OfferState>({
    enabled: false,
    url: '',
    accepted: true,
    loading: true,
    error: null,
  });
  const [offerSubmitting, setOfferSubmitting] = useState(false);

  const isOfferGateOpen = useMemo(() => {
    return offer.loading ? false : offer.enabled && !offer.accepted && !!offer.url;
  }, [offer.accepted, offer.enabled, offer.loading, offer.url]);

  const closeMiniApp = () => {
    const tg = (window as any)?.Telegram?.WebApp;
    if (tg?.close) tg.close();
    else window.close();
  };

  useEffect(() => {
    let cancelled = false;

    const loadOfferStatus = async () => {
      try {
        const st = await apiClient.getOfferStatus();
        if (cancelled) return;

        setOffer({
          enabled: !!st?.enabled,
          url: String(st?.url ?? ''),
          accepted: !!st?.accepted,
          loading: false,
          error: null,
        });
      } catch (e: any) {
        if (cancelled) return;
        // Fail-open: если оферта не загрузилась из-за ошибки API, не блокируем вход.
        console.error('[FirstLaunch] getOfferStatus failed', e);
        setOffer({
          enabled: false,
          url: '',
          accepted: true,
          loading: false,
          error: e?.message || 'Offer status load error',
        });
      }
    };

    void loadOfferStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  const acceptOffer = async () => {
    if (!offer.url || offerSubmitting) return;
    try {
      setOfferSubmitting(true);
      await apiClient.postOfferDecision(true);
      setOffer((p) => ({ ...p, accepted: true, error: null }));
    } catch (e: any) {
      console.error('[FirstLaunch] postOfferDecision(true) failed', e);
      setOffer((p) => ({ ...p, error: e?.message || 'Failed to accept offer' }));
    } finally {
      setOfferSubmitting(false);
    }
  };

  const declineOffer = async () => {
    if (!offer.url || offerSubmitting) return;
    try {
      setOfferSubmitting(true);
      await apiClient.postOfferDecision(false);
    } catch (e: any) {
      // даже если запрос не прошёл — всё равно закрываем mini app, т.к. пользователь отказался
      console.error('[FirstLaunch] postOfferDecision(false) failed', e);
    } finally {
      setOfferSubmitting(false);
      closeMiniApp();
    }
  };

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
    setLanguage(lang); // мгновенно подсвечиваем кнопку
    i18n.changeLanguage(lang); // меняем язык в UI
    void saveLanguage(lang); // асинхронно сохраняем на бэке
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
      {/* --- Offer Gate Modal --- */}
      {isOfferGateOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Offer agreement"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 9999,
          }}
        >
          <div className="card" style={{ width: 'min(520px, 100%)' }}>
            <div className="card-header" style={{ justifyContent: 'space-between' }}>
              <div className="card-title">Публичная оферта</div>
              {/* Крестик не даём — только явное согласие или отмена */}
            </div>

            <div style={{ padding: '0 var(--space-14) var(--space-14) var(--space-14)' as any }}>
              <div style={{ marginTop: 10, opacity: 0.9, lineHeight: 1.4 }}>
                Перед использованием сервиса необходимо ознакомиться с{' '}
                <a
                  href={offer.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    color: 'var(--tg-color-link, var(--tg-color-accent, #2196F3))',
                    textDecoration: 'underline',
                    fontWeight: 600,
                  }}
                >
                  публичной офертой
                </a>{' '}
                и принять её условия.
              </div>

              {!!offer.error && (
                <div
                  className="card"
                  style={{
                    marginTop: 10,
                    background: 'rgba(255, 51, 51, 0.1)',
                    borderColor: 'rgba(255, 51, 51, 0.3)',
                    padding: 10,
                  }}
                >
                  <div style={{ color: 'var(--tg-color-text)', fontSize: 13 }}>{String(offer.error)}</div>
                </div>
              )}

              <div
                style={{
                  marginTop: 12,
                  display: 'flex',
                  gap: 8,
                  justifyContent: 'flex-end',
                  alignItems: 'center',
                  flexWrap: 'nowrap',
                }}
              >
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={declineOffer}
                  disabled={offerSubmitting}
                >
                  Отмена
                </button>

                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={acceptOffer}
                  disabled={offerSubmitting}
                >
                  Согласен
                </button>
              </div>

              {offerSubmitting && (
                <small
                  style={{
                    display: 'block',
                    marginTop: 8,
                    fontSize: 11,
                    color: 'var(--tg-color-text-secondary)',
                    textAlign: 'right',
                  }}
                >
                  Сохранение…
                </small>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Заголовок и приветствие */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardbody">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <img
                src={logo}
                alt="GraceHub"
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 10,
                }}
              />
              <span style={{ fontSize: 22, fontWeight: 600 }}>{t('app.title')}</span>
            </div>

            {/* NEW: Admin button (same markup as in App.tsx bottom menu) */}
            {isSuperadmin && onOpenAdmin && (
              <button
                className="nav-button"
                type="button"
                onClick={onOpenAdmin}
                title="Superadmin"
                style={{
                  padding: 0,
                  width: 44,
                  minWidth: 44,
                  flex: '0 0 auto',
                }}
              >
                <span className="nav-icon">🛡️</span>
                {/* Оставляем тот же nav-label, но скрываем, чтобы было как "иконка" справа сверху */}
                <span className="nav-label" style={{ display: 'none' }}>
                  Admin
                </span>
              </button>
            )}
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
                      border: active ? '1px solid var(--tg-color-accent)' : '1px solid var(--tg-color-hint)',
                      backgroundColor: active ? 'var(--tg-color-accent)' : 'var(--tg-theme-bg-color, #ffffff)',
                      color: active ? '#ffffff' : 'var(--tg-color-text, #000000)',
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
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>{t('firstLaunch.actionsTitle')}</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
              className="btn btn--primary btn--full-width"
              onClick={() => setShowAddModal(true)}
              disabled={isOfferGateOpen}
              title={isOfferGateOpen ? 'Требуется согласие с офертой' : undefined}
            >
              ➕ {t('firstLaunch.addBot')}
            </button>
          </div>
        </div>
      </div>

      {/* Подсказка как начать */}
      <div className="card">
        <div className="cardbody">
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>{t('firstLaunch.howToStartTitle')}</h3>
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

      {showAddModal && <AddBotModal onClose={() => setShowAddModal(false)} onSubmitToken={handleSubmitToken} />}
    </div>
  );
};

export default FirstLaunch;
