// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

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
      await loadOperators();
      setTimeout(() => setSuccess(null), 3000);
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
      {/* Форма добавления */}
      <div className="card">
        <h3 style={{ margin: '0 0 12px 0' }}>{t('operators.add_title')}</h3>

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

          <button className="btn btn-primary btn-block" type="submit">
            {t('operators.add_button')}
          </button>
        </form>
      </div>

      {/* Список операторов */}
      <h3 style={{ marginTop: '16px', marginBottom: '8px' }}>
        {t('operators.list_title', { count: operators.length })}
      </h3>

      {operators.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <p style={{ color: 'var(--tg-color-text-secondary)' }}>
            {t('operators.empty')}
          </p>
        </div>
      ) : (
        operators.map((op) => (
          <div key={op.user_id} className="card">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div className="list-item-title">
                  {op.role === 'owner'
                    ? '👑'
                    : op.role === 'operator'
                    ? '👤'
                    : '👁️'}{' '}
                  {op.username || op.user_id}
                </div>
                <div
                  className="list-item-subtitle"
                  style={{ marginTop: '4px' }}
                >
                  <span
                    className="status-badge"
                    style={{ marginRight: '8px' }}
                  >
                    {op.role}
                  </span>
                  {new Date(op.created_at).toLocaleString(
                    i18n.language === 'ru' ? 'ru-RU' : 'en-US',
                    {
                      month: '2-digit',
                      day: '2-digit',
                    },
                  )}
                </div>
              </div>
              {op.role !== 'owner' && (
                <button
                  className="btn btn-danger btn-sm"
                  onClick={() => handleRemoveOperator(op.user_id, op.username)}
                >
                  {t('operators.remove_button')}
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
};

export default Operators;
