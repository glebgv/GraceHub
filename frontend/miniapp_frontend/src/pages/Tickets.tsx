import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

interface TicketsProps {
  instanceId: string;
}

const Tickets: React.FC<TicketsProps> = ({ instanceId }) => {
  const { t, i18n } = useTranslation();

  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const statuses = [
    { value: '',          label: t('tickets.filter_all') },
    { value: 'new',       label: t('tickets.status_new') },
    { value: 'inprogress',label: t('tickets.status_inprogress') },
    { value: 'answered',  label: t('tickets.status_answered') },
    { value: 'closed',    label: t('tickets.status_closed') },
    { value: 'spam',      label: t('tickets.status_spam') },
  ];

  useEffect(() => {
    const loadTickets = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await apiClient.getTickets(
          instanceId,
          statusFilter || undefined,
          searchQuery || undefined,
        );
        setTickets(data.items || []);
      } catch (err: any) {
        setError(err.message);
        console.error('Ошибка загрузки тикетов:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTickets();
  }, [instanceId, statusFilter, searchQuery]);

  if (loading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center', padding: '32px 12px' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }}></div>
          <p>{t('tickets.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px' }}>
      <div className="card">
        <div className="form-group">
          <label className="form-label">{t('tickets.filter_status_label')}</label>
          <select
            className="form-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {statuses.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">{t('tickets.search_label')}</label>
          <input
            className="form-input"
            type="text"
            placeholder={t('tickets.search_placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {error && (
        <div
          className="card"
          style={{
            background: 'rgba(255, 51, 51, 0.1)',
            borderColor: 'rgba(255, 51, 51, 0.3)',
          }}
        >
          <p style={{ color: 'var(--tg-color-text)', margin: 0 }}>
            {t('tickets.error_prefix')} {error}
          </p>
        </div>
      )}

      {tickets.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>📭</div>
          <p style={{ color: 'var(--tg-color-text-secondary)' }}>
            {t('tickets.empty')}
          </p>
        </div>
      ) : (
        <>
          <div
            style={{
              marginBottom: '8px',
              fontSize: '12px',
              color: 'var(--tg-color-text-secondary)',
            }}
          >
            {t('tickets.total_prefix')} {tickets.length}
          </div>
          {tickets.map((ticket) => (
            <div key={ticket.ticket_id} className="card">
              <div className="list-item">
                <div className="list-item-info" style={{ flex: 1, minWidth: 0 }}>
                  <div className="list-item-title">
                    {ticket.status_emoji} #{ticket.ticket_id}
                  </div>
                  <div className="list-item-subtitle">
                    {ticket.username || t('tickets.user_fallback', { id: ticket.user_id })}
                  </div>
                  <div
                    style={{
                      marginTop: '4px',
                      fontSize: '11px',
                      color: 'var(--tg-color-text-secondary)',
                    }}
                  >
                    {t('tickets.created_at_label')}{' '}
                    {new Date(ticket.created_at).toLocaleString(
                      i18n.language === 'ru' ? 'ru-RU' : 'en-US',
                      {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      },
                    )}
                  </div>
                </div>
                <span
                  className="status-badge"
                  style={{ whiteSpace: 'nowrap', marginLeft: '8px' }}
                >
                  {ticket.status}
                </span>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
};

export default Tickets;
