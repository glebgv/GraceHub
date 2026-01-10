import { useEffect, useState } from 'react';
import { Header } from '../components/common/Header';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { TicketStats } from '../components/Tickets/TicketStats';
import { TicketList } from '../components/Tickets/TicketList';
import HelpdeskAPI from '../api/helpdesk';
import { useTickets } from '../hooks/useTickets';
import type { DashboardStats } from '../types/api';

interface DashboardPageProps {
  api: HelpdeskAPI;
}

export default function DashboardPage({ api }: DashboardPageProps) {
  const { tickets, loading } = useTickets(api);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await api.getDashboardStats();
        setStats(data);
      } catch (error) {
        console.error('Failed to load stats:', error);
      } finally {
        setStatsLoading(false);
      }
    };

    loadStats();
    const interval = setInterval(loadStats, 30000);
    return () => clearInterval(interval);
  }, [api]);

  return (
    <div className="h-screen flex flex-col">
      <Header title="🎫 Helpdesk" />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-4">
          {statsLoading ? (
            <LoadingSpinner />
          ) : stats ? (
            <>
              <TicketStats
                activeCount={stats.activeTickets}
                newCount={stats.newTickets}
                avgResponseTime={Math.round(stats.avgResponseTime)}
              />
              <h2 className="text-lg font-bold mb-4">Последние тикеты</h2>
            </>
          ) : null}

          <TicketList tickets={tickets.slice(0, 5)} loading={loading} />
        </div>
      </div>
    </div>
  );
}
