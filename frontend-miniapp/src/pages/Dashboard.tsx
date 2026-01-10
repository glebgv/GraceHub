// src/pages/Dashboard.tsx
// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTranslation } from 'react-i18next';
import { formatDurationSeconds } from '../utils/formatDuration';
import { PieChart, Pie, Cell, Tooltip, Legend, Text } from 'recharts';

interface DashboardProps {
  instanceId: string;
}

const DashboardSkeleton: React.FC = () => {
  return (
    <div style={{ padding: '12px' }}>
      {/* Карточка со статистикой тикетов */}
      <div className="card">
        {/* Заголовок карточки - скелетон */}
        <div 
          className="skeleton h-6 w-40 mb-4 animate-pulse" 
          style={{ 
            display: 'block', 
            backgroundColor: '#e5e7eb', 
            minHeight: '1.5rem',
            width: '10rem',
            borderRadius: '4px',
            marginBottom: '1rem'
          }}
        ></div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
          }}
        >
          {/* Левая колонка - блоки статистики */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="stat-block">
                {/* stat-label скелетон */}
                <div 
                  className="skeleton h-4 w-24 mb-2 animate-pulse"
                  style={{ 
                    display: 'block', 
                    backgroundColor: '#e5e7eb', 
                    minHeight: '1rem',
                    width: '6rem',
                    borderRadius: '4px',
                    marginBottom: '0.5rem'
                  }}
                ></div>
                {/* stat-value скелетон */}
                <div 
                  className="skeleton h-8 w-16 animate-pulse"
                  style={{ 
                    display: 'block', 
                    backgroundColor: '#e5e7eb', 
                    minHeight: '2rem',
                    width: '4rem',
                    borderRadius: '4px'
                  }}
                ></div>
              </div>
            ))}
          </div>

          {/* Правая колонка - график */}
          <div style={{ height: '250px', position: 'relative' }}>
            {/* Круглый скелетон графика */}
            <div
              className="skeleton animate-pulse rounded-full"
              style={{
                width: '160px',
                height: '160px',
                margin: '20px auto 0',
                backgroundColor: '#e5e7eb',
                display: 'block',
                borderRadius: '9999px'
              }}
            ></div>

            {/* Центральное значение */}
            <div
              className="skeleton h-8 w-16 animate-pulse"
              style={{
                position: 'absolute',
                top: '95px',
                left: '50%',
                transform: 'translateX(-50%)',
                backgroundColor: '#e5e7eb',
                display: 'block',
                minHeight: '2rem',
                width: '4rem',
                borderRadius: '4px'
              }}
            ></div>

            {/* Легенда графика */}
            <div style={{ marginTop: '20px', paddingLeft: '20px' }}>
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    marginBottom: '8px',
                  }}
                >
                  <div 
                    className="skeleton h-4 w-4 mr-2 animate-pulse rounded"
                    style={{ 
                      display: 'block', 
                      backgroundColor: '#e5e7eb', 
                      minHeight: '1rem',
                      width: '1rem',
                      borderRadius: '4px',
                      marginRight: '0.5rem'
                    }}
                  ></div>
                  <div 
                    className="skeleton h-4 w-32 animate-pulse"
                    style={{ 
                      display: 'block', 
                      backgroundColor: '#e5e7eb', 
                      minHeight: '1rem',
                      width: '8rem',
                      borderRadius: '4px'
                    }}
                  ></div>
                  <div 
                    className="skeleton h-4 w-8 ml-auto animate-pulse"
                    style={{ 
                      display: 'block', 
                      backgroundColor: '#e5e7eb', 
                      minHeight: '1rem',
                      width: '2rem',
                      borderRadius: '4px',
                      marginLeft: 'auto'
                    }}
                  ></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Вторая карточка - средний ответ и уникальные пользователи */}
      <div className="card">
        {/* Первый блок - Средний ответ (label) */}
        <div 
          className="skeleton h-4 w-48 mb-2 animate-pulse"
          style={{ 
            display: 'block', 
            backgroundColor: '#e5e7eb', 
            minHeight: '1rem',
            width: '12rem',
            borderRadius: '4px',
            marginBottom: '0.5rem'
          }}
        ></div>
        {/* Первый блок - Средний ответ (value) */}
        <div 
          className="skeleton h-8 w-40 mb-4 animate-pulse"
          style={{ 
            display: 'block', 
            backgroundColor: '#e5e7eb', 
            minHeight: '2rem',
            width: '10rem',
            borderRadius: '4px',
            marginBottom: '1rem'
          }}
        ></div>

        {/* Второй блок - Уникальные пользователи (label) */}
        <div 
          className="skeleton h-4 w-32 mb-2 animate-pulse"
          style={{ 
            display: 'block', 
            backgroundColor: '#e5e7eb', 
            minHeight: '1rem',
            width: '8rem',
            borderRadius: '4px',
            marginBottom: '0.5rem'
          }}
        ></div>
        {/* Второй блок - Уникальные пользователи (value) */}
        <div 
          className="skeleton h-8 w-20 animate-pulse"
          style={{ 
            display: 'block', 
            backgroundColor: '#e5e7eb', 
            minHeight: '2rem',
            width: '5rem',
            borderRadius: '4px'
          }}
        ></div>
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
    // ✅ Не загружаем данные, если instanceId пустой или временный
    if (!instanceId || instanceId === 'temp-loading' || instanceId === '') {
      setLoading(true);
      setStats(null);
      setError(null);
      return;
    }

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

  const avgFirstResponseSec = stats.avg_first_response_sec ?? stats.avgfirstresponsesec ?? 0;
  const uniqueUsers = stats.unique_users ?? stats.uniqueusers ?? 0;

  const avgFirstResponseText = formatDurationSeconds(
    avgFirstResponseSec,
    i18n.resolvedLanguage || i18n.language || 'ru'
  );

  const data = [
    { name: t('dashboard.ticketsNew'), value: tickets.new || 0 },
    { name: t('dashboard.ticketsInProgress'), value: tickets.inprogress || 0 },
    { name: t('dashboard.ticketsAnswered'), value: tickets.answered || 0 },
    { name: t('dashboard.ticketsClosed'), value: tickets.closed || 0 },
  ];

  const total = data.reduce((sum, entry) => sum + entry.value, 0);

  const noDataData = [{ name: 'No Data', value: 1 }];

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];
  const NO_DATA_COLOR = '#CCCCCC';

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
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
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

          <div>
            <PieChart width={200} height={250}>
              <Pie
                data={total > 0 ? data : noDataData}
                cx={100}
                cy={100}
                innerRadius={60}
                outerRadius={80}
                fill="#8884d8"
                paddingAngle={5}
                dataKey="value"
              >
                {total > 0
                  ? data.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))
                  : <Cell key="no-data" fill={NO_DATA_COLOR} />}
              </Pie>
              <Text x={100} y={100} dy={8} textAnchor="middle" fill="#333">
                {total}
              </Text>
              <Tooltip />
              <Legend />
            </PieChart>
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
