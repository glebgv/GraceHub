// src/pages/InstancesList.tsx
import React, { useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { apiClient } from '../api/client';

interface Instance {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
}

type LangCode = 'ru' | 'en' | 'es' | 'hi' | 'zh';

const LANGS: Array<{ code: LangCode; labelKey: string; flagCode: string }> = [
  { code: 'ru', labelKey: 'settings.language_ru', flagCode: 'ru' },
  { code: 'en', labelKey: 'settings.language_en', flagCode: 'gb' }, // можно 'us', если хочешь флаг США
  { code: 'es', labelKey: 'settings.language_es', flagCode: 'es' },
  { code: 'hi', labelKey: 'settings.language_hi', flagCode: 'in' },
  { code: 'zh', labelKey: 'settings.language_zh', flagCode: 'cn' },
];

const FLAG_STYLE: React.CSSProperties = {
  display: 'inline-block',
  width: 20,
  height: 15,
  borderRadius: 3,
  flex: '0 0 auto',
};

interface InstancesListProps {
  instances: Instance[];
  onSelect: (inst: Instance) => void;

  // Открыть UI добавления бота (модалка/экран)
  onAddBotClick?: () => void;

  onOpenSuperAdmin?: () => void;

  // заглушка под удаление; App может просто логгировать или фильтровать список
  onDeleteInstance?: (inst: Instance) => Promise<void> | void;

  /**
   * NEW: если App поймал ошибку лимита (например из createInstanceByToken),
   * он может передать сюда текст, чтобы InstancesList показал красивую модалку.
   * Пример: "⚠️ Достигнут лимит подключаемых ботов: 1/1"
   */
  limitMessage?: string | null;

  /**
   * NEW: коллбек "На главную" из модалки лимита.
   * Обычно это: закрыть add-bot модалку + показать список инстансов.
   */
  onGoHome?: () => void;

  /**
   * NEW: уведомить App, что модалка лимита закрыта (чтобы App сбросил limitMessage).
   */
  onDismissLimitMessage?: () => void;
}

const InstancesList: React.FC<InstancesListProps> = ({
  instances,
  onSelect,
  onAddBotClick,
  onOpenSuperAdmin,
  onDeleteInstance,
  limitMessage,
  onGoHome,
  onDismissLimitMessage,
}) => {
  const { t, i18n } = useTranslation();

  const [instanceToDelete, setInstanceToDelete] = useState<Instance | null>(null);
  const [deleting, setDeleting] = useState(false);

  // локальное состояние модалки лимита (чтобы можно было анимировать/закрывать по клику)
  const [limitModalOpen, setLimitModalOpen] = useState(false);

  // Language dropdown + restart modal
  const [langOpen, setLangOpen] = useState(false);
  const [langSaving, setLangSaving] = useState(false);
  const [langError, setLangError] = useState<string | null>(null);
  const [restartModalOpen, setRestartModalOpen] = useState(false);
  const langWrapRef = useRef<HTMLDivElement | null>(null);

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

  // Language helpers
  const currentLang = ((i18n.language || 'ru') as LangCode) ?? 'ru';
  const currentLangMeta = LANGS.find((l) => l.code === currentLang) ?? LANGS[0];

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const el = langWrapRef.current;
      if (!el) return;
      if (!el.contains(e.target as Node)) setLangOpen(false);
    };

    if (langOpen) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [langOpen]);

  const handlePickLanguage = async (code: LangCode) => {
    setLangOpen(false);
    setLangError(null);

    if (!instances || instances.length === 0) {
      setRestartModalOpen(true);
      return;
    }

    try {
      setLangSaving(true);

      // Вариант A: применяем язык ко всем инстансам аккаунта
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

      // По ТЗ: просим перезагрузку для применения настроек
      setRestartModalOpen(true);
    } catch (e: any) {
      setLangError((t('settings.error_prefix') || 'Ошибка:') + ' ' + (e?.message || String(e)));
    } finally {
      setLangSaving(false);
    }
  };

  const addBotDisabled = deleting || limitModalOpen;

  // Пустой список
  if (!instances || instances.length === 0) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div className="text-center">
          <div style={{ fontSize: '32px', marginBottom: 12 }}>🤖</div>

          <h2 style={{ marginTop: 0 }}>{t('instances.select_instance_title')}</h2>

          <p style={{ color: 'var(--tg-color-text-secondary)', fontSize: 13 }}>
            Здесь будут боты, к которым у вас есть доступ.
          </p>

          <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'center' }}>
            {/* Language dropdown */}
            <div ref={langWrapRef} style={{ position: 'relative' }}>
              <button
                type="button"
                className="btn btn--outline instances-pill"
                onClick={() => setLangOpen((v) => !v)}
                disabled={langSaving}
                aria-label={t('settings.language_title')}
                title={t('settings.language_title')}
                style={{ opacity: langSaving ? 0.7 : 1 }}
              >
                <span
                  aria-hidden
                  className={`fi fi-${currentLangMeta.flagCode}`}
                  style={FLAG_STYLE}
                />
              </button>

              {langOpen && (
                <div
                  className="card"
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 8px)',
                    zIndex: 200,
                    minWidth: 190,
                    padding: 6,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {LANGS.map((l) => (
                    <button
                      key={l.code}
                      type="button"
                      className="btn"
                      onClick={() => handlePickLanguage(l.code)}
                      disabled={langSaving}
                      style={{
                        width: '100%',
                        display: 'flex',
                        gap: 10,
                        alignItems: 'center',
                        justifyContent: 'flex-start',
                        padding: '8px 10px',
                        border: 'none',
                        background: 'transparent',
                        opacity: langSaving ? 0.7 : 1,
                      }}
                    >
                      <span aria-hidden className={`fi fi-${l.flagCode}`} style={FLAG_STYLE} />
                      <span>{t(l.labelKey)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {onOpenSuperAdmin && (
              <button type="button" onClick={onOpenSuperAdmin} className="btn btn--secondary">
                <span aria-hidden>🛡</span> <span>Admin</span>
              </button>
            )}

            {onAddBotClick && (
              <button
                type="button"
                onClick={onAddBotClick}
                className="btn btn--primary"
                disabled={addBotDisabled}
                title={addBotDisabled ? 'Недоступно во время операции' : undefined}
              >
                <span aria-hidden>➕</span> <span>Бот</span>
              </button>
            )}
          </div>

          {langError && (
            <div
              className="card"
              style={{
                marginTop: 10,
                background: 'rgba(255, 51, 51, 0.1)',
                borderColor: 'rgba(255, 51, 51, 0.3)',
              }}
            >
              <p style={{ margin: 0, color: 'var(--tg-color-text)' }}>{langError}</p>
            </div>
          )}
        </div>

        {/* Модалка лимита (показывается даже если список пустой) */}
        {limitModalOpen && normalizedLimitText && (
          <div className="modal-backdrop" onClick={closeLimitModal}>
            <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 360 }}>
              <div className="modal-header">
                <h2 className="modal-title">Ограничение</h2>
                <button
                  className="modal-close"
                  onClick={closeLimitModal}
                  type="button"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <p style={{ marginBottom: 12 }}>{normalizedLimitText}</p>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                  На главную
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Модалка: нужен перезапуск */}
        {restartModalOpen && (
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t('settings.restart_required_title') || 'Требуется перезапуск'}
            onClick={(e) => {
              if (e.target === e.currentTarget) setRestartModalOpen(false);
            }}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.45)',
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 12,
            }}
          >
            <div
              className="card"
              style={{ width: '100%', maxWidth: 520, borderRadius: 12 }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ margin: '0 0 8px 0' }}>
                {t('settings.restart_required_title') || 'Требуется перезапуск'}
              </h3>

              <p style={{ margin: '0 0 12px 0', color: 'var(--tg-color-text)' }}>
                {t('settings.restart_required_text') ||
                  'Язык был изменён. Чтобы изменения применились везде, перезапустите приложение.'}
              </p>

              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => window.location.reload()}
                  style={{ flex: 1 }}
                >
                  {t('settings.restart_now') || 'Перезапустить сейчас'}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setRestartModalOpen(false)}
                  style={{
                    flex: 1,
                    background: 'var(--tg-theme-secondary-bg-color)',
                  }}
                >
                  {t('settings.restart_later') || 'Позже'}
                </button>
              </div>

              <small
                style={{
                  display: 'block',
                  marginTop: 10,
                  color: 'var(--tg-color-text-secondary)',
                }}
              >
                {t('settings.restart_hint') ||
                  'Если не перезапускать, часть интерфейса может остаться на старом языке.'}
              </small>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Нормальный список
  return (
    <div className="instances-page">
      <div className="instances-top">
        <div className="instances-title">
          <h2 className="instances-h2">{t('instances.select_instance_title')}</h2>
          <div className="instances-subtitle">
            {t('instances.available_count', { count: instances.length })}
          </div>
        </div>

        <div className="instances-actions">
          {/* Language dropdown — right top */}
          <div ref={langWrapRef} style={{ position: 'relative' }}>
            <button
              type="button"
              className="btn btn--outline instances-pill"
              onClick={() => setLangOpen((v) => !v)}
              disabled={langSaving}
              aria-label={t('settings.language_title')}
              title={t('settings.language_title')}
              style={{ opacity: langSaving ? 0.7 : 1 }}
            >
              <span
                aria-hidden
                className={`fi fi-${currentLangMeta.flagCode}`}
                style={FLAG_STYLE}
              />
            </button>

            {langOpen && (
              <div
                className="card"
                style={{
                  position: 'absolute',
                  right: 0,
                  top: 'calc(100% + 8px)',
                  zIndex: 200,
                  minWidth: 190,
                  padding: 6,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    type="button"
                    className="btn"
                    onClick={() => handlePickLanguage(l.code)}
                    disabled={langSaving}
                    style={{
                      width: '100%',
                      display: 'flex',
                      gap: 10,
                      alignItems: 'center',
                      justifyContent: 'flex-start',
                      padding: '8px 10px',
                      border: 'none',
                      background: 'transparent',
                      opacity: langSaving ? 0.7 : 1,
                    }}
                  >
                    <span aria-hidden className={`fi fi-${l.flagCode}`} style={FLAG_STYLE} />
                    <span>{t(l.labelKey)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

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
              onClick={onAddBotClick}
              className="btn btn--primary instances-pill"
              disabled={addBotDisabled}
              title={addBotDisabled ? 'Недоступно во время операции' : undefined}
              style={{ opacity: addBotDisabled ? 0.7 : 1 }}
            >
              <span aria-hidden>➕</span>
              <span>Бот</span>
            </button>
          )}
        </div>

        {langError && (
          <div
            className="card"
            style={{
              marginTop: 10,
              background: 'rgba(255, 51, 51, 0.1)',
              borderColor: 'rgba(255, 51, 51, 0.3)',
            }}
          >
            <p style={{ margin: 0, color: 'var(--tg-color-text)' }}>{langError}</p>
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
                  style={{ opacity: deleting ? 0.7 : 1 }}
                >
                  🗑
                </button>
              )}
            </div>
          </button>
        ))}
      </div>

      {/* Модальное окно подтверждения удаления */}
      {instanceToDelete && (
        <div className="modal-backdrop" onClick={() => !deleting && setInstanceToDelete(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 360 }}>
            <div className="modal-header">
              <h2 className="modal-title">Удалить бота?</h2>
              <button
                className="modal-close"
                onClick={() => setInstanceToDelete(null)}
                type="button"
                aria-label="Close"
                disabled={deleting}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <p style={{ marginBottom: 12 }}>Вы действительно хотите удалить инстанс:</p>
              <p style={{ fontWeight: 600, marginBottom: 4 }}>{instanceToDelete.botname}</p>
              <p style={{ marginTop: 0, fontSize: 13, color: 'var(--tg-color-text-secondary)' }}>
                @{instanceToDelete.botusername}
              </p>
            </div>

            <div className="modal-footer">
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
        </div>
      )}

      {/* Модалка лимита поверх списка */}
      {limitModalOpen && normalizedLimitText && (
        <div className="modal-backdrop" onClick={closeLimitModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 360 }}>
            <div className="modal-header">
              <h2 className="modal-title">Ограничение</h2>
              <button
                className="modal-close"
                onClick={closeLimitModal}
                type="button"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: 12 }}>{normalizedLimitText}</p>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                На главную
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модалка: нужен перезапуск */}
      {restartModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t('settings.restart_required_title') || 'Требуется перезапуск'}
          onClick={(e) => {
            if (e.target === e.currentTarget) setRestartModalOpen(false);
          }}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 12,
          }}
        >
          <div
            className="card"
            style={{ width: '100%', maxWidth: 520, borderRadius: 12 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 8px 0' }}>
              {t('settings.restart_required_title') || 'Требуется перезапуск'}
            </h3>

            <p style={{ margin: '0 0 12px 0', color: 'var(--tg-color-text)' }}>
              {t('settings.restart_required_text') ||
                'Язык был изменён. Чтобы изменения применились везде, перезапустите приложение.'}
            </p>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => window.location.reload()}
                style={{ flex: 1 }}
              >
                {t('settings.restart_now') || 'Перезапустить сейчас'}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setRestartModalOpen(false)}
                style={{ flex: 1 }}
              >
                {t('settings.restart_later') || 'Позже'}
              </button>
            </div>

            <small
              style={{
                display: 'block',
                marginTop: 10,
                color: 'var(--tg-color-text-secondary)',
              }}
            >
              {t('settings.restart_hint') ||
                'Если не перезапускать, часть интерфейса может остаться на старом языке.'}
            </small>
          </div>
        </div>
      )}
    </div>
  );
};

export default InstancesList;
