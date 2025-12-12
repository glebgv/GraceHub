// src/pages/Dashboard.tsx
import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

interface DashboardProps {
  instanceId: string;
  onOpenBilling?: () => void; // НОВЫЙ ПРОП
}

const Dashboard: React.FC<DashboardProps> = ({ instanceId, onOpenBilling }) => {
  const { t } = useTranslation();

  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await apiClient.getStats(instanceId);
        setStats(data);
        setError(null);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadStats();
  }, [instanceId]);

  if (loading) {
    return <div className="card">{t('dashboard.loading')}</div>;
  }

  if (error) {
    return (
      <div className="card" style={{ color: 'red' }}>
        {t('dashboard.errorPrefix')}: {error}
      </div>
    );
  }

  if (!stats) {
    return <div className="card">{t('dashboard.noData')}</div>;
  }

  const tickets = stats.tickets_by_status || {};
  const usage = stats.usage || {};

  return (
    <div style={{ padding: '12px' }}>
      <div className="card">
        <div className="card-title">{t('dashboard.ticketsTitle')}</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
            marginTop: '12px',
          }}
        >
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.ticketsNew')}</div>
            <div className="stat-value">{tickets.new || 0}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.ticketsInProgress')}</div>
            <div className="stat-value">{tickets.inprogress || 0}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.ticketsAnswered')}</div>
            <div className="stat-value">{tickets.answered || 0}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.ticketsClosed')}</div>
            <div className="stat-value">{tickets.closed || 0}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">{t('dashboard.usageTitle')}</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
            marginTop: '12px',
          }}
        >
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.usageMessages')}</div>
            <div className="stat-value">{usage.messages || 0}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">{t('dashboard.usageApiCalls')}</div>
            <div className="stat-value">{usage.api_calls || 0}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="stat-label">{t('dashboard.avgResponseLabel')}</div>
        <div className="stat-value">{stats.avg_first_response_sec || 0}s</div>
        <div className="stat-label" style={{ marginTop: '12px' }}>
          {t('dashboard.uniqueUsersLabel')}
        </div>
        <div className="stat-value">{stats.unique_users || 0}</div>
      </div>

      {/* НОВАЯ КАРТОЧКА ТАРИФА */}
      <div className="card tariff-card">
        <div className="card-title">
          {t('dashboard.tariffTitle') ?? 'Тариф и оплата'}
        </div>
        <div className="stat-label" style={{ marginTop: '8px' }}>
          {t('dashboard.tariffDescription') ??
            'Управляйте тарифом и оплатой бота'}
        </div>
        <button
          className="btn"
          style={{ marginTop: '12px', width: '100%' }}
          onClick={() => onOpenBilling && onOpenBilling()}
        >
          {t('dashboard.openBillingButton') ?? 'Открыть тарифы'}
        </button>
      </div>
    </div>
  );
};

export default Dashboard;
