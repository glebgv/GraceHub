// src/pages/FirstLaunch.tsx
// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useMemo, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';
import { apiClient } from '../api/client';
import AddBotModal from '../components/AddBotModal';
import logo from '../assets/logo.png';
import { FaPlus, FaCreditCard } from 'react-icons/fa';

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

interface FirstLaunchProps {
  onAddBotClick: (token: string) => Promise<void> | void;
  instanceId?: string | null;
  isSuperadmin?: boolean;
  onOpenAdmin?: () => void;
  onGoToBilling?: () => void;
  loading?: boolean;
}

type OfferState = {
  enabled: boolean;
  url: string;
  accepted: boolean;
  loading: boolean;
  error: string | null;
};

const LANGS: Array<{ code: LangCode; label: string; flagCode: string }> = [
  { code: 'ru', label: 'Русский', flagCode: 'ru' },
  { code: 'en', label: 'English', flagCode: 'gb' },
  { code: 'es', label: 'Español', flagCode: 'es' },
  { code: 'hi', label: 'हिन्दी', flagCode: 'in' },
  { code: 'zh', label: '中文', flagCode: 'cn' },
];

const FLAGSTYLE: React.CSSProperties = {
  display: 'inline-block',
  width: 20,
  height: 15,
  borderRadius: 3,
  flex: '0 0 auto',
};

// Telegram Bot Token validation regex
const TELEGRAM_BOT_TOKEN_REGEX = /^[0-9]{8,10}:[a-zA-Z0-9_-]{35}$/;

const validateTelegramBotToken = (token: string): boolean => {
  if (!token || typeof token !== 'string') {
    return false;
  }
  const trimmedToken = token.trim();
  return TELEGRAM_BOT_TOKEN_REGEX.test(trimmedToken);
};

const getTokenErrorMessage = (language: LangCode): string => {
  const errorMessages: Record<LangCode, string> = {
    ru: 'Неверный формат токена',
    en: 'Invalid token format',
    es: 'Formato de token no válido',
    hi: 'अमान्य टोकन प्रारूप',
    zh: '令牌格式无效',
  };
  return errorMessages[language] || errorMessages.en;
};

const FirstLaunchSkeleton: React.FC = () => {
  return (
    <div style={{ padding: 12 }}>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <div className="skeleton" style={{ width: 32, height: 32, borderRadius: 10 }} />
            <div className="skeleton animate-pulse" style={{ width: 120, height: 24 }} />
          </div>

          <div className="skeleton animate-pulse" style={{ width: '100%', height: 16, marginBottom: 6 }} />
          <div className="skeleton animate-pulse" style={{ width: '80%', height: 14, marginBottom: 12 }} />

          <div className="skeleton animate-pulse" style={{ width: 100, height: 12, marginBottom: 6 }} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton animate-pulse" style={{ width: 80, height: 32, borderRadius: 999 }} />
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body">
          <div className="skeleton animate-pulse" style={{ width: 140, height: 18, marginBottom: 10 }} />
          <div style={{ display: 'flex', flexDirection: 'row', gap: 8 }}>
            <div className="skeleton animate-pulse" style={{ flex: 1, height: 44, borderRadius: 10 }} />
            <div className="skeleton animate-pulse" style={{ flex: 1, height: 44, borderRadius: 10 }} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card__body">
          <div className="skeleton animate-pulse" style={{ width: 160, height: 18, marginBottom: 10 }} />
          <div style={{ paddingLeft: 18 }}>
            <div className="skeleton animate-pulse" style={{ width: '90%', height: 14, marginBottom: 8 }} />
            <div className="skeleton animate-pulse" style={{ width: '85%', height: 14, marginBottom: 8 }} />
            <div className="skeleton animate-pulse" style={{ width: '88%', height: 14 }} />
          </div>
        </div>
      </div>
    </div>
  );
};

const FirstLaunch: React.FC<FirstLaunchProps> = ({
  onAddBotClick,
  instanceId,
  isSuperadmin,
  onOpenAdmin,
  onGoToBilling,
  loading = false,
}) => {
  const { t, i18n } = useTranslation();

  // Читаем user_language из URL параметров (передаётся из бота)
  const urlParams = new URLSearchParams(window.location.search);
  const passedLangParam = urlParams.get('user_language');
  const passedLang = (passedLangParam as LangCode) || null;

  // Инициализируем язык: 1) из URL, 2) из i18n, 3) 'ru'
  const initialLang: LangCode = passedLang || (i18n.language as LangCode) || 'ru';
  
  const [language, setLanguage] = useState<LangCode>(initialLang);
  const [userLanguage, setUserLanguage] = useState<LangCode>(initialLang);

  const [showAddModal, setShowAddModal] = useState(false);
  const [addBotError, setAddBotError] = useState<string | null>(null);

  // --- Offer gate state ---
  const [offer, setOffer] = useState<OfferState>({
    enabled: false,
    url: '',
    accepted: true,
    loading: true,
    error: null,
  });

  const [offerSubmitting, setOfferSubmitting] = useState(false);
  
  // Ref для отслеживания монтирования
  const mountedRef = useRef(true);
  const offerLoadedRef = useRef(false);

  const isOfferGateOpen = useMemo(() => {
    return offer.loading ? false : offer.enabled && !offer.accepted && !!offer.url;
  }, [offer.accepted, offer.enabled, offer.loading, offer.url]);

  const closeMiniApp = () => {
    const tg = (window as any)?.Telegram?.WebApp;
    if (tg?.close) tg.close();
    else window.close();
  };

  // Инициализируем язык в i18n при монтировании
  useEffect(() => {
    if (LANGS.some(lang => lang.code === initialLang)) {
      i18n.changeLanguage(initialLang);
    }
  }, [i18n, initialLang]);

  useEffect(() => {
    mountedRef.current = true;
    offerLoadedRef.current = false;
    
    const loadOfferStatus = async () => {
      // Не загружаем если уже загрузили или идет внешняя загрузка
      if (offerLoadedRef.current || loading) {
        return;
      }
      
      try {
        console.log('[FirstLaunch] Loading offer status...');
        const st = await apiClient.getOfferStatus();
        
        if (!mountedRef.current) return;
        
        console.log('[FirstLaunch] Offer status loaded:', st);
        offerLoadedRef.current = true;
        
        setOffer({
          enabled: !!st?.enabled,
          url: String(st?.url ?? ''),
          accepted: !!st?.accepted,
          loading: false,
          error: null,
        });
      } catch (e: any) {
        if (!mountedRef.current) return;
        
        console.error('[FirstLaunch] getOfferStatus failed', e);
        offerLoadedRef.current = true;
        
        setOffer({
          enabled: false,
          url: '',
          accepted: true,
          loading: false,
          error: null, // fail-open
        });
      }
    };

    // Используем задержку для предотвращения скачков рендера
    const timeoutId = setTimeout(() => {
      void loadOfferStatus();
    }, 150);

    return () => {
      mountedRef.current = false;
      clearTimeout(timeoutId);
    };
  }, [loading]); // Добавляем зависимость от loading

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
      console.error('[FirstLaunch] postOfferDecision(false) failed', e);
    } finally {
      setOfferSubmitting(false);
      closeMiniApp();
    }
  };

  // Язык меняется локально и сохраняем на бэкенде
  const handleLanguageClick = async (lang: LangCode) => {
    try {
      // Обновляем локальное состояние ПЕРЕД сменой языка в i18n
      setLanguage(lang);
      setUserLanguage(lang);
      
      // Меняем язык в i18n
      await i18n.changeLanguage(lang);
      
      // Сохраняем язык в базу данных
      await apiClient.saveUserLanguage(lang);
    } catch (e: any) {
      console.error('[FirstLaunch] Failed to save language', e);
      // Можно показать уведомление об ошибке
    }
  };

  const handleSubmitToken = async (token: string) => {
    setAddBotError(null);
    try {
      const trimmedToken = token.trim();
      await onAddBotClick(trimmedToken);
      setShowAddModal(false);
    } catch (err: any) {
      console.error('[FirstLaunch] Add bot failed', err);
      setAddBotError(err?.message || 'Ошибка при добавлении бота');
      // Модалка остаётся открытой, чтобы пользователь увидел ошибку в AddBotModal (если там есть)
    }
  };

  // Показ скелетона только во время загрузки оферты или внешнего loading
  if (loading) {
    return <FirstLaunchSkeleton />;
  }

  return (
    <div style={{ padding: 12 }}>
      {/* Offer Gate - Drawer */}
      <Drawer.Root open={isOfferGateOpen} dismissible={false}>
        <Drawer.Portal>
          <Drawer.Overlay className="fixed inset-0 bg-black/40" style={{ zIndex: 9998 }} />
          <Drawer.Content
            className="fixed bottom-0 left-0 right-0 flex flex-col rounded-t-[16px] outline-none"
            style={{
              zIndex: 9999,
              maxHeight: '60vh',
              backgroundColor: 'var(--tg-theme-bg-color, #ffffff)',
            }}
          >
            <div
              style={{
                width: 40,
                height: 4,
                borderRadius: 999,
                background: 'var(--tg-theme-hint-color, rgba(0,0,0,0.3))',
                margin: '12px auto',
                flexShrink: 0,
              }}
            />

            <div className="overflow-y-auto p-4" style={{ WebkitOverflowScrolling: 'touch' }}>
              <div className="mx-auto max-w-md">
                <Drawer.Title
                  style={{
                    marginBottom: 12,
                    fontSize: 18,
                    fontWeight: 600,
                    color: 'var(--tg-theme-text-color, #000000)',
                  }}
                >
                  Публичная оферта
                </Drawer.Title>

                <div style={{ marginBottom: 16, opacity: 0.9, lineHeight: 1.4, fontSize: 14 }}>
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
                    style={{
                      marginBottom: 16,
                      padding: 12,
                      borderRadius: 10,
                      background: 'rgba(255, 51, 51, 0.1)',
                      border: '1px solid rgba(255, 51, 51, 0.3)',
                    }}
                  >
                    <div style={{ color: 'var(--tg-color-text)', fontSize: 13 }}>
                      {String(offer.error)}
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 8 }}>
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
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body">
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
              <img src={logo} alt="GraceHub" style={{ width: 32, height: 32, borderRadius: 10 }} />
              <span style={{ fontSize: 22, fontWeight: 600 }}>{t('app.title')}</span>
            </div>

            {isSuperadmin && onOpenAdmin && (
              <button
                className="nav-button"
                type="button"
                onClick={onOpenAdmin}
                title="Superadmin"
                style={{ padding: 0, width: 44, minWidth: 44, flex: '0 0 auto' }}
              >
                <span className="nav-icon">🛡️</span>
                <span className="nav-label" style={{ display: 'none' }}>
                  Admin
                </span>
              </button>
            )}
          </div>

          <p style={{ margin: 0, fontSize: 14, color: 'var(--tg-color-text-secondary)' }}>
            {t('firstLaunch.welcome')}
          </p>
          <p style={{ marginTop: 6, marginBottom: 0, fontSize: 13, color: 'var(--tg-color-text-secondary)' }}>
            {t('firstLaunch.description')}
          </p>

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

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {LANGS.map((item) => {
                const active = language === item.code;

                return (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => handleLanguageClick(item.code)}
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
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    aria-label={item.label}
                    title={item.label}
                  >
                    <span
                      aria-hidden
                      className={`fi fi-${item.flagCode}`}
                      style={{
                        ...FLAGSTYLE,
                        filter: active ? 'saturate(1.05) brightness(1.05)' : undefined,
                      }}
                    />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body">
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>{t('firstLaunch.actionsTitle')}</h3>

          {onGoToBilling ? (
            <div style={{ display: 'flex', flexDirection: 'row', gap: 8 }}>
              <button
                className="btn btn--primary"
                style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                onClick={() => setShowAddModal(true)}
                disabled={isOfferGateOpen}
              >
                <FaPlus size={20} color="white" />
                {t('firstLaunch.addBot')}
              </button>

              <button
                className="btn btn--secondary"
                style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                onClick={onGoToBilling}
                disabled={isOfferGateOpen}
              >
                <FaCreditCard size={20} color="var(--tg-theme-text-color, #000000)" />
                {t('nav.billing')}
              </button>
            </div>
          ) : (
            <button
              className="btn btn--primary btn--full-width"
              onClick={() => setShowAddModal(true)}
              disabled={isOfferGateOpen}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
            >
              <FaPlus size={20} color="white" />
              {t('firstLaunch.addBot')}
            </button>
          )}

          {addBotError && (
            <div
              style={{
                marginTop: 12,
                padding: 10,
                background: 'rgba(255, 51, 51, 0.1)',
                borderRadius: 8,
                fontSize: 13,
                color: 'var(--tg-color-destructive-text, #ff3b30)',
              }}
            >
              {addBotError}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card__body">
          <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 16 }}>{t('firstLaunch.howToStartTitle')}</h3>

          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 14, color: 'var(--tg-color-text-secondary)' }}>
            <li>{t('firstLaunch.step1')}</li>
            <li>{t('firstLaunch.step2')}</li>
            <li>{t('firstLaunch.step3')}</li>
          </ol>
        </div>
      </div>

      <AddBotModal
        open={showAddModal}
        onClose={() => {
          setShowAddModal(false);
          setAddBotError(null);
        }}
        onSubmitToken={handleSubmitToken}
        validateToken={validateTelegramBotToken}
        getErrorMessage={() => getTokenErrorMessage(language)}
      />
    </div>
  );
};

export { validateTelegramBotToken, getTokenErrorMessage };
export default FirstLaunch;