// src/pages/InstancesList.tsx
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
  loading?: boolean;
}

const InstancesListSkeleton: React.FC = () => {
  return (
    <div style={{ padding: 12 }}>
      {/* Top section with title and actions */}
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

        {/* Action buttons skeleton */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <div
            className="skeleton animate-pulse"
            style={{ width: 44, height: 36, borderRadius: 999 }}
          />
          <div
            className="skeleton animate-pulse"
            style={{ width: 100, height: 36, borderRadius: 999 }}
          />
          <div
            className="skeleton animate-pulse"
            style={{ width: 120, height: 36, borderRadius: 999 }}
          />
        </div>
      </div>

      {/* Instance cards skeleton */}
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

  const normalizedLimitText = useMemo(() => {
    const txt = (limitMessage ?? '').trim();
    return txt.length ? txt : '';
  }, [limitMessage]);

  useEffect(() => {
    setLimitModalOpen(!!normalizedLimitText);
  }, [normalizedLimitText]);

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
    } finally {
      setDeleting(false);
      setInstanceToDelete(null);
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
    await apiClient.post('/instances', { token });
    window.location.reload();
  };

  const handleAddBotClick = () => {
    setAddBotModalOpen(true);
    onAddBotClick?.();
  };

  const closeAddBotModal = () => {
    setAddBotModalOpen(false);
  };

  const addBotDisabled = deleting || limitModalOpen;

  const isEmpty = !instances || instances.length === 0;

  // Loading or deleting state (Skeleton)
  if (loading || deleting) {
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

              {onOpenSuperAdmin && (
                <button
                  type="button"
                  onClick={onOpenSuperAdmin}
                  className="btn btn--secondary instances-pill"
                >
                  <span aria-hidden>🛡</span>
                  <span>Admin</span>
                </button>
              )}

              {onAddBotClick && (
                <button
                  type="button"
                  onClick={handleAddBotClick}
                  className="btn btn--primary instances-pill"
                  disabled={addBotDisabled}
                  title={addBotDisabled ? 'Недоступно во время операции' : undefined}
                >
                  <span aria-hidden>➕</span>
                  <span>{t('instances.bot')}</span>
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
              </div>

              <div className="instances-actions">
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

                {onOpenSuperAdmin && (
                  <button
                    type="button"
                    onClick={onOpenSuperAdmin}
                    className="btn btn--secondary instances-pill"
                  >
                    <span aria-hidden>🛡</span>
                    <span>Admin</span>
                  </button>
                )}

                {onAddBotClick && (
                  <button
                    type="button"
                    onClick={handleAddBotClick}
                    className="btn btn--primary instances-pill"
                    disabled={addBotDisabled}
                    title={addBotDisabled ? 'Недоступно во время операции' : undefined}
                  >
                    <span aria-hidden>➕</span>
                    <span>{t('instances.bot')}</span>
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
                <button
                  key={inst.instanceid}
                  type="button"
                  className="card instance-card"
                  onClick={() => onSelect(inst)}
                >
                  <div className="instance-left">
                    <div className="instance-name">
                      <span className="instance-emoji" aria-hidden>
                        🤖
                      </span>
                      <span className="instance-name-text">{inst.botname}</span>
                    </div>
                    <div className="instance-username">@{inst.botusername}</div>
                  </div>

                  <div className="instance-right" onClick={(e) => e.stopPropagation()}>
                    <span className="instance-badge">{inst.role}</span>

                    {onDeleteInstance && (
                      <button
                        type="button"
                        aria-label="Delete"
                        title="Delete"
                        onClick={() => setInstanceToDelete(inst)}
                        className="btn btn--outline btn--sm instance-trash"
                        disabled={deleting}
                      >
                        🗑
                      </button>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* AddBotModal с контролируемым состоянием */}
      <AddBotModal
        open={addBotModalOpen}
        onClose={closeAddBotModal}
        onSubmitToken={handleSubmitToken}
        validateToken={validateTelegramBotToken}
        getErrorMessage={() => getTokenErrorMessage(currentLang)}
      />

      {/* Shared Language Picker Drawer */}
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
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <div className="drawer-handle" />

              <h3 className="drawer-title">🌐 {t('settings.language_title')}</h3>

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

      {/* Delete Confirmation Drawer (conditional) */}
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
            <Drawer.Content className="drawer-content">
              <div className="drawer-body">
                <div className="drawer-handle" />

                <h3 className="drawer-title">🗑️ Удалить бота?</h3>

                <div className="drawer-text">
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

      {/* Shared Limit Modal */}
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
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <div className="drawer-handle" />

              <h3 className="drawer-title">⚠️ Ограничение</h3>

              <p className="drawer-text">{normalizedLimitText}</p>

              <div className="drawer-footer drawer-footer-end">
                <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                  На главную
                </button>
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Shared Restart Modal */}
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
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <div className="drawer-handle" />

              <h3 className="drawer-title">
                🔄 {t('settings.restart_required_title') || 'Требуется перезапуск'}
              </h3>

              <p className="drawer-text">
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
    </>
  );
};

export default InstancesList;
