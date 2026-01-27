// src/pages/InstancesList.tsx
// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../api/client';
import { Drawer } from 'vaul';
import AddBotModal from '../components/AddBotModal';
import { validateTelegramBotToken, getTokenErrorMessage } from './FirstLaunch';

interface Instance {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
}

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

const LANGS: Array<{ code: LangCode; labelKey: string; flagCode: string }> = [
  { code: 'ru', labelKey: 'settings.language_ru', flagCode: 'ru' },
  { code: 'en', labelKey: 'settings.language_en', flagCode: 'gb' },
  { code: 'es', labelKey: 'settings.language_es', flagCode: 'es' },
  { code: 'hi', labelKey: 'settings.language_hi', flagCode: 'in' },
  { code: 'zh', labelKey: 'settings.language_zh', flagCode: 'cn' },
];

interface InstancesListProps {
  instances: Instance[];
  onSelect: (inst: Instance) => void;
  onAddBotClick?: () => void;
  onOpenSuperAdmin?: () => void;
  onDeleteInstance?: (inst: Instance) => Promise<void> | void;
  limitMessage?: string | null;
  onGoHome?: () => void;
  onDismissLimitMessage?: () => void;
  onGoToBilling?: () => void;
  loading?: boolean;
}

interface UserSubscription {
  plan_code: string;
  plan_name: string;
  period_start: string;
  period_end: string;
  days_left: number;
  instances_limit: number;
  instances_created: number;
  unlimited: boolean;
}

const InstancesListSkeleton: React.FC = () => {
  return (
    <div style={{ padding: 12 }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 12 }}>
          <div
            className="skeleton animate-pulse"
            style={{ width: 200, height: 28, marginBottom: 8, borderRadius: 6 }}
          />
          <div
            className="skeleton animate-pulse"
            style={{ width: 150, height: 16, borderRadius: 4 }}
          />
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <div
            className="skeleton animate-pulse"
            style={{ width: 44, height: 36, borderRadius: 999 }}
          />
          <div
            className="skeleton animate-pulse"
            style={{ width: 100, height: 36, borderRadius: 999 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="card"
            style={{
              padding: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div
                  className="skeleton animate-pulse"
                  style={{ width: 20, height: 20, borderRadius: 4 }}
                />
                <div
                  className="skeleton animate-pulse"
                  style={{ width: 140, height: 18, borderRadius: 4 }}
                />
              </div>
              <div
                className="skeleton animate-pulse"
                style={{ width: 100, height: 14, borderRadius: 4 }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                className="skeleton animate-pulse"
                style={{ width: 60, height: 24, borderRadius: 12 }}
              />
              <div
                className="skeleton animate-pulse"
                style={{ width: 36, height: 36, borderRadius: 8 }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const InstancesList: React.FC<InstancesListProps> = ({
  instances,
  onSelect,
  onAddBotClick,
  onOpenSuperAdmin,
  onDeleteInstance,
  limitMessage,
  onGoHome,
  onDismissLimitMessage,
  onGoToBilling,
  loading = false,
}) => {
  const { t, i18n } = useTranslation();

  const [instanceToDelete, setInstanceToDelete] = useState<Instance | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [limitModalOpen, setLimitModalOpen] = useState(false);

  const [langOpen, setLangOpen] = useState(false);
  const [langSaving, setLangSaving] = useState(false);
  const [langError, setLangError] = useState<string | null>(null);
  const [restartModalOpen, setRestartModalOpen] = useState(false);

  const [addBotModalOpen, setAddBotModalOpen] = useState(false);
  const [addBotError, setAddBotError] = useState<string | null>(null);

  const [subscription, setSubscription] = useState<UserSubscription | null>(null);
  const [loadingSubscription, setLoadingSubscription] = useState(true);
  const [expiredModalOpen, setExpiredModalOpen] = useState(false);

  const normalizedLimitText = useMemo(() => {
    const txt = (limitMessage ?? '').trim();
    return txt.length ? txt : '';
  }, [limitMessage]);

  useEffect(() => {
    setLimitModalOpen(!!normalizedLimitText);
  }, [normalizedLimitText]);

  // Загрузка подписки пользователя
  useEffect(() => {
    const loadSubscription = async () => {
      try {
        setLoadingSubscription(true);
        const sub = await apiClient.getUserSubscription();
        setSubscription(sub);

        if (sub.days_left <= 0 && instances.length > 0) {
          setExpiredModalOpen(true);
        }
      } catch (e: any) {
        console.error('[InstancesList] Failed to load user subscription:', e);
        setSubscription(null);
      } finally {
        setLoadingSubscription(false);
      }
    };

    loadSubscription();
  }, [instances.length]);

  const closeLimitModal = () => {
    setLimitModalOpen(false);
    onDismissLimitMessage?.();
  };

  const goHomeFromLimitModal = () => {
    closeLimitModal();
    onGoHome?.();
  };

  const handleConfirmDelete = async () => {
    if (!instanceToDelete || !onDeleteInstance) {
      setInstanceToDelete(null);
      return;
    }

    try {
      setDeleting(true);
      await onDeleteInstance(instanceToDelete);
      setInstanceToDelete(null);
    } catch (error) {
      console.error('[InstancesList] Delete failed:', error);
    } finally {
      setDeleting(false);
    }
  };

  const currentLang = ((i18n.language || 'ru') as LangCode) ?? 'ru';
  const currentLangMeta = LANGS.find((l) => l.code === currentLang) ?? LANGS[0];

  const handlePickLanguage = async (code: LangCode) => {
    setLangOpen(false);
    setLangError(null);

    if (!instances || instances.length === 0) {
      setRestartModalOpen(true);
      return;
    }

    try {
      setLangSaving(true);

      const results = await Promise.allSettled(
        instances.map((inst) => apiClient.updateSettings(inst.instanceid, { language: code }))
      );

      const failedCount = results.filter((r) => r.status === 'rejected').length;
      if (failedCount > 0) {
        setLangError(
          t('settings.error_prefix') ||
            `Не удалось обновить язык для части ботов (${failedCount}/${instances.length}).`
        );
      }

      setRestartModalOpen(true);
    } catch (e: any) {
      setLangError((t('settings.error_prefix') || 'Ошибка:') + ' ' + (e?.message || String(e)));
    } finally {
      setLangSaving(false);
    }
  };

  const handleSubmitToken = async (token: string) => {
    try {
      setAddBotError(null);
      await apiClient.createInstanceByToken({ 
        token,
        language: i18n.language 
      });
      window.location.reload();
    } catch (err: any) {
      console.error('[InstancesList] Add bot failed', err);
      setAddBotError(err?.message || 'Ошибка при добавлении бота');
      throw err;
    }
  };

  const handleAddBotClick = () => {
    setAddBotError(null);
    setAddBotModalOpen(true);
    onAddBotClick?.();
  };

  const closeAddBotModal = () => {
    setAddBotModalOpen(false);
    setAddBotError(null);
  };

  const addBotDisabled = deleting;

  const isEmpty = !instances || instances.length === 0;

  // ✅ Ключевое исправление: показываем скелетон только при начальной загрузке,
  const shouldShowSkeleton = loading && instances.length > 0 && !deleting;

  if (shouldShowSkeleton || loadingSubscription) {
    return <InstancesListSkeleton />;
  }

  return (
    <>
      <div className={isEmpty ? 'app-container instances-empty' : 'instances-page'}>
        {isEmpty ? (
          <div className="instances-empty-content">
            <div className="instances-empty-icon" aria-hidden="true">
              🤖
            </div>

            <h2 className="instances-empty-title">{t('instances.select_instance_title')}</h2>

            <p className="instances-empty-subtitle">
              Здесь будут боты, к которым у вас есть доступ.
            </p>

            <div className="instances-empty-actions">
              <div style={{ 
                display: 'flex', 
                gap: '8px', 
                marginBottom: '12px',
                justifyContent: 'center'
              }}>
                <button
                  type="button"
                  className="btn btn--outline instances-pill"
                  onClick={() => setLangOpen(true)}
                  disabled={langSaving}
                  aria-label={t('settings.language_title')}
                  title={t('settings.language_title')}
                >
                  <span aria-hidden className={`fi fi-${currentLangMeta.flagCode} flag-icon`} />
                </button>

                {onAddBotClick && (
                  <button
                    type="button"
                    onClick={handleAddBotClick}
                    className="btn btn--primary instances-pill"
                    disabled={deleting}
                    title={deleting ? 'Недоступно во время операции' : undefined}
                  >
                    <span aria-hidden>➕</span>
                    <span>{t('instances.bot')}</span>
                  </button>
                )}
              </div>

              {onOpenSuperAdmin && (
                <button
                  type="button"
                  onClick={onOpenSuperAdmin}
                  className="btn btn--secondary instances-pill"
                  style={{ 
                    width: '100%', 
                    justifyContent: 'center',
                    maxWidth: '200px',
                    margin: '0 auto'
                  }}
                >
                  <span aria-hidden>🛡</span>
                  <span>Admin</span>
                </button>
              )}
            </div>

            {langError && (
              <div className="card error-card">
                <p className="error-text">{langError}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="instances-top">
              <div className="instances-title">
                <h2 className="instances-h2">{t('instances.select_instance_title')}</h2>
                <div className="instances-subtitle">
                  {t('instances.available_count', { count: instances.length })}
                </div>

                {subscription && (
                  <div
                    className="subscription-info"
                    style={{
                      marginTop: 8,
                      fontSize: 14,
                      color: subscription.days_left > 0 ? 'var(--tg-color-text-secondary)' : '#ff4444',
                      fontWeight: subscription.days_left <= 0 ? 'bold' : 'normal',
                    }}
                  >
                    {subscription.days_left > 0
                      ? t('instances.subscription_days_left', { days: subscription.days_left }) ||
                        `Осталось дней: ${subscription.days_left}`
                      : t('instances.subscription_expired') || 'Подписка истекла'}
                  </div>
                )}
              </div>

              <div className="instances-actions" style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '8px',
                alignItems: 'stretch'
              }}>
                {/* Первая строка: язык и бот в одной строке */}
                <div style={{ 
                  display: 'flex', 
                  gap: '8px',
                  justifyContent: 'flex-start'
                }}>
                  <button
                    type="button"
                    className="btn btn--outline instances-pill"
                    onClick={() => setLangOpen(true)}
                    disabled={langSaving}
                    aria-label={t('settings.language_title')}
                    title={t('settings.language_title')}
                  >
                    <span aria-hidden className={`fi fi-${currentLangMeta.flagCode} flag-icon`} />
                  </button>

                  {onAddBotClick && (
                    <button
                      type="button"
                      onClick={handleAddBotClick}
                      className="btn btn--primary instances-pill"
                      disabled={deleting}
                      title={deleting ? 'Недоступно во время операции' : undefined}
                    >
                      <span aria-hidden>➕</span>
                      <span>{t('instances.bot')}</span>
                    </button>
                  )}
                </div>

                {/* Вторая строка: админка */}
                {onOpenSuperAdmin && (
                  <button
                    type="button"
                    onClick={onOpenSuperAdmin}
                    className="btn btn--secondary instances-pill"
                    style={{ 
                      width: '100%', 
                      justifyContent: 'center',
                      maxWidth: '200px'
                    }}
                  >
                    <span aria-hidden>🛡</span>
                    <span>Admin</span>
                  </button>
                )}
              </div>

              {langError && (
                <div className="card error-card">
                  <p className="error-text">{langError}</p>
                </div>
              )}
            </div>

            <div className="instances-grid">
              {instances.map((inst) => (
                <div
                  key={inst.instanceid}
                  role="button"
                  tabIndex={0}
                  className="card instance-card"
                  onClick={() => !deleting && onSelect(inst)}
                  onKeyDown={(e) => {
                    if (!deleting && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      onSelect(inst);
                    }
                  }}
                  style={{ 
                    cursor: deleting ? 'not-allowed' : 'pointer',
                    opacity: deleting ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '16px',
                    gap: '12px',
                    borderRadius: '12px',
                    backgroundColor: 'var(--tg-background-secondary)',
                    border: '1px solid var(--tg-border-color)',
                    transition: 'all 0.2s ease'
                  }}
                  aria-disabled={deleting}
                >
                  <div style={{ 
                    flex: 1, 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '4px',
                    overflow: 'hidden'
                  }}>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px' 
                    }}>
                      <span style={{ 
                        fontSize: '18px',
                        lineHeight: 1
                      }} aria-hidden>
                        🤖
                      </span>
                      <span style={{ 
                        fontSize: '16px',
                        fontWeight: '600',
                        color: 'var(--tg-color-text-primary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {inst.botname}
                      </span>
                    </div>
                    <div style={{ 
                      fontSize: '14px',
                      color: 'var(--tg-color-text-secondary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      @{inst.botusername}
                    </div>
                  </div>

                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '8px',
                    flexShrink: 0
                  }} onClick={(e) => e.stopPropagation()}>
                    <span style={{ 
                      padding: '4px 10px',
                      borderRadius: '12px',
                      backgroundColor: 'var(--tg-background-tertiary)',
                      color: 'var(--tg-color-text-primary)',
                      fontSize: '13px',
                      fontWeight: '500',
                      border: '1px solid var(--tg-border-color)'
                    }}>
                      {inst.role}
                    </span>

                    {onDeleteInstance && (
                      <button
                        type="button"
                        aria-label="Delete"
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          setInstanceToDelete(inst);
                        }}
                        style={{
                          background: 'transparent',
                          border: '1px solid var(--tg-border-color)',
                          borderRadius: '8px',
                          width: '36px',
                          height: '36px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                          color: 'var(--tg-color-text-secondary)',
                          transition: 'all 0.2s ease',
                          flexShrink: 0
                        }}
                        disabled={deleting}
                        onMouseEnter={(e) => {
                          if (!deleting) {
                            e.currentTarget.style.backgroundColor = 'var(--tg-background-tertiary)';
                            e.currentTarget.style.color = '#ff4444';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!deleting) {
                            e.currentTarget.style.backgroundColor = 'transparent';
                            e.currentTarget.style.color = 'var(--tg-color-text-secondary)';
                          }
                        }}
                      >
                        🗑
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* AddBotModal */}
      <AddBotModal
        open={addBotModalOpen}
        onClose={closeAddBotModal}
        onSubmitToken={handleSubmitToken}
        validateToken={validateTelegramBotToken}
        getErrorMessage={() => getTokenErrorMessage(currentLang)}
      />

      {/* Language Picker Drawer */}
      <Drawer.Root
        open={langOpen}
        onOpenChange={(open) => {
          setLangOpen(open);
        }}
        modal
        dismissible={true}
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content" aria-describedby={undefined}>
            <Drawer.Title className="drawer-title">
              🌐 {t('settings.language_title')}
            </Drawer.Title>

            <div className="drawer-body">
              <div className="drawer-handle" />

              <div className="drawer-list">
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    type="button"
                    className={`drawer-list-item ${currentLang === l.code ? 'active' : ''}`}
                    onClick={() => handlePickLanguage(l.code)}
                    disabled={langSaving}
                  >
                    <span aria-hidden className={`fi fi-${l.flagCode} flag-icon`} />
                    <span className="drawer-list-item-text">{t(l.labelKey)}</span>
                    {currentLang === l.code && (
                      <span className="drawer-list-item-check" aria-hidden>
                        ✓
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Delete Confirmation Drawer */}
      {!!instanceToDelete && (
        <Drawer.Root
          open={!!instanceToDelete}
          onOpenChange={(open) => {
            if (!open && !deleting) setInstanceToDelete(null);
          }}
          modal
          dismissible={true}
        >
          <Drawer.Portal>
            <Drawer.Overlay className="drawer-overlay" />
            <Drawer.Content className="drawer-content" aria-describedby="delete-description">
              <Drawer.Title className="drawer-title">
                🗑️ Удалить бота?
              </Drawer.Title>

              <div className="drawer-body">
                <div className="drawer-handle" />

                <div className="drawer-text" id="delete-description">
                  <p className="drawer-text-line">Вы действительно хотите удалить инстанс:</p>
                  <p className="drawer-text-strong">{instanceToDelete?.botname}</p>
                  <p className="drawer-text-hint">@{instanceToDelete?.botusername}</p>
                </div>

                <div className="drawer-footer">
                  <button
                    type="button"
                    className="btn btn--outline"
                    onClick={() => setInstanceToDelete(null)}
                    disabled={deleting}
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={handleConfirmDelete}
                    disabled={deleting}
                  >
                    {deleting ? 'Удаляем…' : 'Удалить'}
                  </button>
                </div>
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      )}

      {/* Limit Modal */}
      <Drawer.Root
        open={limitModalOpen && !!normalizedLimitText}
        onOpenChange={(open) => {
          if (!open) closeLimitModal();
        }}
        modal
        dismissible={true}
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content" aria-describedby="limit-description">
            <Drawer.Title className="drawer-title">
              ⚠️ Ограничение
            </Drawer.Title>

            <div className="drawer-body">
              <div className="drawer-handle" />

              <p className="drawer-text" id="limit-description">
                {normalizedLimitText}
              </p>

              <div className="drawer-footer drawer-footer-end">
                <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                  На главную
                </button>
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Restart Modal */}
      <Drawer.Root
        open={restartModalOpen}
        onOpenChange={(open) => {
          if (!open) setRestartModalOpen(false);
        }}
        modal
        dismissible={true}
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content" aria-describedby="restart-description">
            <Drawer.Title className="drawer-title">
              🔄 {t('settings.restart_required_title') || 'Требуется перезапуск'}
            </Drawer.Title>

            <div className="drawer-body">
              <div className="drawer-handle" />

              <p className="drawer-text" id="restart-description">
                {t('settings.restart_required_text') ||
                  'Язык был изменён. Чтобы изменения применились везде, перезапустите приложение.'}
              </p>

              <div className="drawer-footer">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => window.location.reload()}
                >
                  {t('settings.restart_now') || 'Перезапустить сейчас'}
                </button>
                <button
                  type="button"
                  className="btn btn--outline"
                  onClick={() => setRestartModalOpen(false)}
                >
                  {t('settings.restart_later') || 'Позже'}
                </button>
              </div>

              <small className="drawer-hint">
                {t('settings.restart_hint') ||
                  'Если не перезапускать, часть интерфейса может остаться на старом языке.'}
              </small>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Модалка при истекшей демо-подписке */}
      <Drawer.Root
        open={expiredModalOpen}
        onOpenChange={(open) => setExpiredModalOpen(open)}
        modal
        dismissible={false}
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content" aria-describedby="expired-description">
            <Drawer.Title className="drawer-title">
              ⚠️ {t('billing.demo_expired_title') || 'Демо-подписка истекла'}
            </Drawer.Title>

            <div className="drawer-body">
              <div className="drawer-handle" />

              <p className="drawer-text" id="expired-description">
                {t('billing.demo_expired_message') ||
                  'Ваша демо-подписка закончилась. Чтобы продолжить использовать ботов, выберите платный тариф.'}
              </p>

              <div className="drawer-footer">
                <button
                  type="button"
                  className="btn btn--outline"
                  onClick={() => setExpiredModalOpen(false)}
                >
                  {t('common.later') || 'Позже'}
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => {
                    setExpiredModalOpen(false);
                    onGoToBilling?.();
                  }}
                >
                  {t('nav.billing') || 'Выбрать тариф'}
                </button>
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </>
  );
};

export default InstancesList;