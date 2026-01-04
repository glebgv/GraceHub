// src/pages/Dashboard.tsx
import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';
import { formatDurationSeconds } from '../utils/formatDuration';

interface DashboardProps {
  instanceId: string;
}

const DashboardSkeleton: React.FC = () => {
  return (
    <div style={{ padding: '12px' }}>
      <div className="card">
        <div className="skeleton h-6 w-40 mb-4 animate-pulse"></div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
          }}
        >
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="stat-block">
              <div className="skeleton h-4 w-24 mb-2 animate-pulse"></div>
              <div className="skeleton h-8 w-16 animate-pulse"></div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="skeleton h-6 w-32 mb-4 animate-pulse"></div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
          }}
        >
          {[1, 2].map((i) => (
            <div key={i} className="stat-block">
              <div className="skeleton h-4 w-24 mb-2 animate-pulse"></div>
              <div className="skeleton h-8 w-16 animate-pulse"></div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="skeleton h-4 w-48 mb-2 animate-pulse"></div>
        <div className="skeleton h-8 w-40 mb-4 animate-pulse"></div>

        <div className="skeleton h-4 w-32 mb-2 animate-pulse"></div>
        <div className="skeleton h-8 w-20 animate-pulse"></div>
      </div>
    </div>
  );
};

const Dashboard: React.FC<DashboardProps> = ({ instanceId }) => {
  const { t, i18n } = useTranslation();

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
    return <DashboardSkeleton />;
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

  const tickets = stats.tickets_by_status || stats.ticketsbystatus || {};
  const usage = stats.usage || {};

  const avgFirstResponseSec = stats.avg_first_response_sec ?? stats.avgfirstresponsesec ?? 0;
  const uniqueUsers = stats.unique_users ?? stats.uniqueusers ?? 0;

  const apiCalls = usage.api_calls ?? usage.apicalls ?? 0;
  const messages = usage.messages ?? 0;

  const avgFirstResponseText = formatDurationSeconds(
    avgFirstResponseSec,
    i18n.resolvedLanguage || i18n.language || 'ru'
  );

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
        <div className="stat-value">{avgFirstResponseText}</div>

        <div className="stat-label" style={{ marginTop: '12px' }}>
          {t('dashboard.uniqueUsersLabel')}
        </div>
        <div className="stat-value">{uniqueUsers}</div>
      </div>
    </div>
  );
};

export default Dashboard;
