// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';
import { FiPlus, FiX, FiCheck, FiTrash2, FiUser, FiEye, FiAward } from 'react-icons/fi';

interface OperatorsProps {
  instanceId: string;
}

interface Operator {
  user_id: number;
  username?: string;
  role: string;
  created_at: string;
}

const Operators: React.FC<OperatorsProps> = ({ instanceId }) => {
  const { t, i18n } = useTranslation();

  const [operators, setOperators] = useState<Operator[]>([]);
  const [loading, setLoading] = useState(true);
  const [newUserId, setNewUserId] = useState('');
  const [newRole, setNewRole] = useState('operator');
  const [error, setError] = useState<string | null>(null);
  const [showAddDrawer, setShowAddDrawer] = useState(false);
  const [showRemoveDrawer, setShowRemoveDrawer] = useState(false);
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [operatorToRemove, setOperatorToRemove] = useState<{ userId: number; username?: string } | null>(null);

  useEffect(() => {
    loadOperators();
  }, [instanceId]);

  const loadOperators = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getOperators(instanceId);
      setOperators(data);
      setError(null);
    } catch (err: any) {
      setError(err.message);
      console.error('Ошибка загрузки операторов:', err);
    } finally {
      setLoading(false);
    }
  };

  const showSuccessNotification = (message: string) => {
    setSuccessMessage(message);
    setShowSuccessToast(true);
    setTimeout(() => {
      setShowSuccessToast(false);
    }, 2500);
  };

  const handleAddOperator = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserId.trim()) {
      setError(t('operators.enter_telegram_id'));
      return;
    }

    try {
      setError(null);
      const userId = parseInt(newUserId);
      await apiClient.addOperator(instanceId, userId, newRole);
      
      // Закрываем drawer и очищаем форму
      setShowAddDrawer(false);
      setNewUserId('');
      setNewRole('operator');
      
      // Обновляем список и показываем уведомление
      await loadOperators();
      showSuccessNotification(t('operators.add_success'));
    } catch (err: any) {
      setError(`${t('operators.error_prefix')} ${err.message}`);
    }
  };

  const openRemoveDrawer = (userId: number, username?: string) => {
    setOperatorToRemove({ userId, username });
    setShowRemoveDrawer(true);
  };

  const confirmRemoveOperator = async () => {
    if (!operatorToRemove) return;

    try {
      setError(null);
      await apiClient.removeOperator(instanceId, operatorToRemove.userId);
      
      // Закрываем drawer удаления
      setShowRemoveDrawer(false);
      setOperatorToRemove(null);
      
      // Обновляем список и показываем уведомление
      await loadOperators();
      showSuccessNotification(t('operators.remove_success'));
    } catch (err: any) {
      setError(`${t('operators.error_prefix')} ${err.message}`);
    }
  };

  const getRoleIcon = (role: string) => {
    if (role === 'owner') return <FiAward style={{ color: '#FFD700' }} />;
    if (role === 'operator') return <FiUser style={{ color: '#007AFF' }} />;
    return <FiEye style={{ color: '#8E8E93' }} />;
  };

  const getRoleText = (role: string) => {
    if (role === 'owner') return 'Owner';
    if (role === 'operator') return 'Operator';
    return 'Viewer';
  };

  if (loading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }}></div>
          <p>{t('operators.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px' }}>
      {/* Заголовок с иконкой добавления */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <h3 style={{ margin: '0' }}>
          {t('operators.list_title', { count: operators.length })}
        </h3>
        <button
          type="button"
          className="btn btn--icon"
          onClick={() => setShowAddDrawer(true)}
          aria-label={t('operators.add_title')}
          style={{ fontSize: '20px', padding: '8px' }}
        >
          <FiPlus />
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: '8px',
            background: 'rgba(255, 51, 51, 0.1)',
            borderRadius: '8px',
            marginBottom: '12px',
            fontSize: '12px',
            color: 'var(--tg-color-text)',
          }}
        >
          {error}
        </div>
      )}

      {operators.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <p style={{ color: 'var(--tg-color-text-secondary)' }}>
            {t('operators.empty')}
          </p>
        </div>
      ) : (
        <div className="operators-list">
          {operators.map((op) => (
            <div key={op.user_id} className="operator-card">
              <div className="operator-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1 }}>
                  <div style={{ fontSize: '20px', display: 'flex', alignItems: 'center' }}>
                    {getRoleIcon(op.role)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '4px' }}>
                      {op.username || `ID: ${op.user_id}`}
                    </div>
                    <div style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color, #999)' }}>
                      {getRoleText(op.role)}
                    </div>
                  </div>
                </div>
                {op.role !== 'owner' && (
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={() => openRemoveDrawer(op.user_id, op.username)}
                    style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <FiTrash2 size={14} />
                    {t('operators.remove_button')}
                  </button>
                )}
              </div>
              
              <div className="operator-details">
                <div className="detail-row">
                  <span className="detail-label">{t('operators.table_id')}:</span>
                  <span className="detail-value">{op.user_id}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t('operators.table_added')}:</span>
                  <span className="detail-value">
                    {new Date(op.created_at).toLocaleString(
                      i18n.language === 'ru' ? 'ru-RU' : 'en-US',
                      {
                        month: '2-digit',
                        day: '2-digit',
                        year: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      },
                    )}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Drawer для добавления оператора */}
      <Drawer.Root
        open={showAddDrawer}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddDrawer(false);
            setError(null);
            setNewUserId('');
            setNewRole('operator');
          }
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <Drawer.Handle className="drawer-handle" />

              <div className="drawer-header">
                <h3 className="drawer-title">{t('operators.add_title')}</h3>
                <button
                  type="button"
                  onClick={() => setShowAddDrawer(false)}
                  className="drawer-close-btn"
                  aria-label="Close"
                >
                  <FiX />
                </button>
              </div>

              {error && (
                <div
                  style={{
                    padding: '8px',
                    background: 'rgba(255, 51, 51, 0.1)',
                    borderRadius: '8px',
                    marginBottom: '12px',
                    fontSize: '12px',
                    color: 'var(--tg-color-text)',
                  }}
                >
                  {error}
                </div>
              )}

              <form onSubmit={handleAddOperator}>
                <div className="form-group">
                  <label className="form-label">
                    {t('operators.telegram_id_label')} *
                  </label>
                  <input
                    className="form-input"
                    type="number"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    placeholder="123456789"
                    required
                  />
                  <small
                    style={{
                      color: 'var(--tg-color-text-secondary)',
                      marginTop: '4px',
                      display: 'block',
                    }}
                  >
                    {t('operators.telegram_id_hint')}
                  </small>
                </div>

                <div className="form-group">
                  <label className="form-label">{t('operators.role_label')}</label>
                  <select
                    className="form-select"
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                  >
                    <option value="operator">
                      {t('operators.role_operator')}
                    </option>
                    <option value="viewer">
                      {t('operators.role_viewer')}
                    </option>
                  </select>
                </div>

                <div className="drawer-footer">
                  <button className="btn btn--primary" type="submit">
                    {t('operators.add_button')}
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={() => setShowAddDrawer(false)}
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              </form>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Drawer для подтверждения удаления */}
      <Drawer.Root
        open={showRemoveDrawer}
        onOpenChange={(open) => {
          if (!open) {
            setShowRemoveDrawer(false);
            setOperatorToRemove(null);
          }
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <Drawer.Handle className="drawer-handle" />

              <div className="drawer-header">
                <h3 className="drawer-title">{t('operators.remove_confirm_title') || 'Удалить оператора?'}</h3>
                <button
                  type="button"
                  onClick={() => setShowRemoveDrawer(false)}
                  className="drawer-close-btn"
                  aria-label="Close"
                >
                  <FiX />
                </button>
              </div>

              <div style={{ padding: '16px 0', fontSize: '14px', color: 'var(--tg-theme-text-color)' }}>
                {t('operators.remove_confirm', {
                  name: operatorToRemove?.username || operatorToRemove?.userId || '',
                })}
              </div>

              <div className="drawer-footer">
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={confirmRemoveOperator}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}
                >
                  <FiTrash2 size={16} />
                  {t('operators.remove_button')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={() => setShowRemoveDrawer(false)}
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Toast уведомление об успехе */}
      <Drawer.Root
        open={showSuccessToast}
        onOpenChange={setShowSuccessToast}
        modal={false}
      >
        <Drawer.Portal>
          <Drawer.Content 
            className="drawer-content success-toast"
            style={{
              maxHeight: 'auto',
              pointerEvents: 'none',
            }}
          >
            <div style={{
              padding: '16px 20px',
              background: 'var(--tg-theme-bg-color, #fff)',
              borderRadius: '12px 12px 0 0',
              boxShadow: '0 -2px 16px rgba(0, 0, 0, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}>
              <FiCheck size={20} style={{ color: '#34C759' }} />
              <span style={{ 
                fontSize: '15px', 
                fontWeight: '500',
                color: 'var(--tg-theme-text-color, #000)',
              }}>
                {successMessage}
              </span>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </div>
  );
};

export default Operators;
