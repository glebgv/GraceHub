import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Instance {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
}

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
  console.log('[InstancesList] instances prop:', instances);
  const { t } = useTranslation();

  const [instanceToDelete, setInstanceToDelete] = useState<Instance | null>(null);
  const [deleting, setDeleting] = useState(false);

  // локальное состояние модалки лимита (чтобы можно было анимировать/закрывать по клику)
  const [limitModalOpen, setLimitModalOpen] = useState(false);

  const normalizedLimitText = useMemo(() => {
    const t = (limitMessage ?? '').trim();
    return t.length ? t : '';
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

  const addBotDisabled = deleting || limitModalOpen;

  if (!instances || instances.length === 0) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div className="text-center">
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>📂</div>
          <h2>Нет инстансов для выбора</h2>
          <p style={{ color: 'var(--tg-color-text-secondary)', fontSize: '13px' }}>
            Здесь будут боты, к которым у вас есть доступ.
          </p>

          <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'center' }}>
            {onOpenSuperAdmin && (
              <button type="button" onClick={onOpenSuperAdmin} className="btn btn--secondary">
                🛡 Admin
              </button>
            )}

            {onAddBotClick && (
              <button
                type="button"
                onClick={onAddBotClick}
                className="btn btn--primary"
                disabled={addBotDisabled}
                title={addBotDisabled ? 'Сейчас действие недоступно' : 'Добавить бота'}
              >
                ➕ Бот
              </button>
            )}
          </div>
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

                <div className="modal-footer">
                  <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                    На главную
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

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
              title={addBotDisabled ? 'Сейчас действие недоступно' : 'Добавить бота'}
              style={{ opacity: addBotDisabled ? 0.7 : 1 }}
            >
              <span aria-hidden>➕</span>
              <span>Бот</span>
            </button>
          )}
        </div>
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
                  aria-label="Удалить бота"
                  title="Удалить бота"
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

              <div className="modal-footer">
                <button type="button" className="btn btn--primary" onClick={goHomeFromLimitModal}>
                  На главную
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InstancesList;
