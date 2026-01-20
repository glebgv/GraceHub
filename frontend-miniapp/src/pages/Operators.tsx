// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';

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
  const [success, setSuccess] = useState<string | null>(null);
  const [showAddDrawer, setShowAddDrawer] = useState(false);

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

  const handleAddOperator = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserId.trim()) {
      setError(t('operators.enter_telegram_id'));
      return;
    }

    try {
      setError(null);
      setSuccess(null);
      const userId = parseInt(newUserId);
      await apiClient.addOperator(instanceId, userId, newRole);
      setSuccess(t('operators.add_success'));
      setNewUserId('');
      setNewRole('operator');
      await loadOperators();
      setTimeout(() => {
        setSuccess(null);
        setShowAddDrawer(false);
      }, 3000);
    } catch (err: any) {
      setError(`${t('operators.error_prefix')} ${err.message}`);
    }
  };

  const handleRemoveOperator = async (userId: number, username?: string) => {
    const confirmMsg = t('operators.remove_confirm', {
      name: username || userId,
    });
    if (!confirm(confirmMsg)) return;

    try {
      setError(null);
      await apiClient.removeOperator(instanceId, userId);
      setSuccess(t('operators.remove_success'));
      await loadOperators();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(`${t('operators.error_prefix')} ${err.message}`);
    }
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
          style={{ fontSize: '20px', padding: '4px 8px' }}
        >
          ➕
        </button>
      </div>

      {success && (
        <div
          style={{
            padding: '8px',
            background: 'rgba(76, 175, 80, 0.1)',
            borderRadius: '8px',
            marginBottom: '12px',
            fontSize: '12px',
            color: 'var(--tg-color-text)',
          }}
        >
          {success}
        </div>
      )}

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
        <div className="table-responsive">
          <table className="table">
            <thead>
              <tr>
                <th>{t('operators.table_id')}</th>
                <th>{t('operators.table_username')}</th>
                <th>{t('operators.table_role')}</th>
                <th>{t('operators.table_added')}</th>
                <th>{t('operators.table_actions')}</th>
              </tr>
            </thead>
            <tbody>
              {operators.map((op) => (
                <tr key={op.user_id}>
                  <td>{op.user_id}</td>
                  <td>{op.username || '—'}</td>
                  <td>
                    {op.role === 'owner'
                      ? '👑 Owner'
                      : op.role === 'operator'
                      ? '👤 Operator'
                      : '👁️ Viewer'}
                  </td>
                  <td>
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
                  </td>
                  <td>
                    {op.role !== 'owner' && (
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleRemoveOperator(op.user_id, op.username)}
                      >
                        {t('operators.remove_button')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Drawer для добавления оператора */}
      <Drawer.Root
        open={showAddDrawer}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddDrawer(false);
            setError(null);
            setSuccess(null);
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
                  ✕
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

              {success && (
                <div
                  style={{
                    padding: '8px',
                    background: 'rgba(76, 175, 80, 0.1)',
                    borderRadius: '8px',
                    marginBottom: '12px',
                    fontSize: '12px',
                    color: 'var(--tg-color-text)',
                  }}
                >
                  {success}
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
                      👤 {t('operators.role_operator')}
                    </option>
                    <option value="viewer">
                      👁️ {t('operators.role_viewer')}
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
    </div>
  );
};

export default Operators;