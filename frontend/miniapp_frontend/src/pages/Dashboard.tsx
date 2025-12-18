// src/pages/Dashboard.tsx
import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';

interface DashboardProps {
  instanceId: string;
}

const Dashboard: React.FC<DashboardProps> = ({ instanceId }) => {
  const { t } = useTranslation();

  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const statsData = await apiClient.getStats(instanceId);

        if (cancelled) return;

        setStats(statsData);
        setError(null);
      } catch (err: any) {
        if (cancelled) return;
        setError(err?.message || 'Unknown error');
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    };

    load();

    return () => {
      cancelled = true;
    };
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

  // Бекенд отдаёт ticketsbystatus / avgfirstresponsesec / uniqueusers / usage.apicalls
  // Но в UI раньше использовались snake_case поля — оставляем поддержку обоих вариантов, чтобы не ломать.
  const tickets = stats.tickets_by_status || stats.ticketsbystatus || {};
  const usage = stats.usage || {};

  const avgFirstResponseSec = stats.avg_first_response_sec ?? stats.avgfirstresponsesec ?? 0;
  const uniqueUsers = stats.unique_users ?? stats.uniqueusers ?? 0;

  const apiCalls = usage.api_calls ?? usage.apicalls ?? 0;
  const messages = usage.messages ?? 0;

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
            <div className="stat-value">{messages}</div>
          </div>

          <div className="stat-block">
            <div className="stat-label">{t('dashboard.usageApiCalls')}</div>
            <div className="stat-value">{apiCalls}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="stat-label">{t('dashboard.avgResponseLabel')}</div>
        <div className="stat-value">{avgFirstResponseSec}s</div>

        <div className="stat-label" style={{ marginTop: '12px' }}>
          {t('dashboard.uniqueUsersLabel')}
        </div>
        <div className="stat-value">{uniqueUsers}</div>
      </div>
    </div>
  );
};

export default Dashboard;
