import React, { useState } from 'react';

interface Instance {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
}

interface InstancesListProps {
  instances: Instance[];
  onSelect: (inst: Instance) => void;
  onAddBotClick?: () => void;
  onOpenSuperAdmin?: () => void; // ✅ NEW
  // заглушка под удаление; App может просто логгировать или фильтровать список
  onDeleteInstance?: (inst: Instance) => Promise<void> | void;
}

const InstancesList: React.FC<InstancesListProps> = ({
  instances,
  onSelect,
  onAddBotClick,
  onOpenSuperAdmin,
  onDeleteInstance,
}) => {
  console.log('[InstancesList] instances prop:', instances);

  const [instanceToDelete, setInstanceToDelete] = useState<Instance | null>(null);
  const [deleting, setDeleting] = useState(false);

  if (!instances || instances.length === 0) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div className="text-center">
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>📂</div>
          <h2>Нет инстансов для выбора</h2>
          <p style={{ color: 'var(--tg-color-text-secondary)', fontSize: '13px' }}>
            Здесь будут боты, к которым у вас есть доступ.
          </p>

          {/* ✅ NEW: кнопка SuperAdmin даже когда нет инстансов */}
          {onOpenSuperAdmin && (
            <div style={{ marginTop: 12 }}>
              <button type="button" onClick={onOpenSuperAdmin} className="btn btn--secondary">
                🛡 Admin
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const handleConfirmDelete = async () => {
    if (!instanceToDelete || !onDeleteInstance) {
      setInstanceToDelete(null);
      return;
    }
    try {
      setDeleting(true);
      await onDeleteInstance(instanceToDelete); // здесь пока заглушка/колбэк в App
    } finally {
      setDeleting(false);
      setInstanceToDelete(null);
    }
  };

  return (
    <div style={{ padding: '12px' }}>
      <div
        style={{
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>Выберите инстанс</h2>
          <p
            style={{
              margin: '4px 0 0 0',
              fontSize: '12px',
              color: 'var(--tg-color-text-secondary)',
            }}
          >
            {instances.length} доступных
          </p>
        </div>

        {/* ✅ NEW: правая группа кнопок */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {onOpenSuperAdmin && (
            <button
              type="button"
              onClick={onOpenSuperAdmin}
              className="btn btn--secondary"
              style={{
                padding: '4px 10px',
                fontSize: 14,
                borderRadius: 999,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                whiteSpace: 'nowrap',
              }}
            >
              <span>🛡</span>
              <span>Admin</span>
            </button>
          )}

          {onAddBotClick && (
            <button
              type="button"
              onClick={onAddBotClick}
              className="btn btn--primary"
              style={{
                padding: '4px 10px',
                fontSize: 14,
                borderRadius: 999,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                whiteSpace: 'nowrap',
              }}
            >
              <span>➕</span>
              <span>Бот</span>
            </button>
          )}
        </div>
      </div>

      {instances.map((inst) => (
        <div
          key={inst.instanceid}
          className="card"
          style={{ cursor: 'pointer', transition: 'all 200ms', position: 'relative' }}
          onClick={() => onSelect(inst)}
          onTouchEnd={() => onSelect(inst)}
        >
          <div className="list-item">
            <div className="list-item-info">
              <div className="list-item-title">
                <span style={{ marginRight: '8px' }}>🤖</span>
                {inst.botname}
              </div>
              <div className="list-item-subtitle">@{inst.botusername}</div>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
              onClick={(e) => e.stopPropagation()} // чтобы клик по корзине не выбирал инстанс
            >
              <span className="instance-badge">{inst.role}</span>

              {onDeleteInstance && (
                <button
                  type="button"
                  aria-label="Удалить бота"
                  title="Удалить бота"
                  onClick={() => setInstanceToDelete(inst)}
                  className="btn btn--outline btn--sm"
                  style={{
                    padding: '4px 8px',
                    borderRadius: 999,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 14,
                  }}
                >
                  🗑
                </button>
              )}
            </div>
          </div>
        </div>
      ))}

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
              <p
                style={{
                  marginTop: 0,
                  fontSize: 13,
                  color: 'var(--tg-color-text-secondary)',
                }}
              >
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
    </div>
  );
};

export default InstancesList;
