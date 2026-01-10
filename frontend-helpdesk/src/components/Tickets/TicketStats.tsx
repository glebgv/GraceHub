import { TrendingUp, AlertCircle } from 'lucide-react';

interface TicketStatsProps {
  activeCount: number;
  newCount: number;
  avgResponseTime: number;
}

export function TicketStats({ activeCount, newCount, avgResponseTime }: TicketStatsProps) {
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      <div className="bg-blue-50 dark:bg-blue-900 rounded-lg p-3">
        <div className="text-2xl font-bold text-blue-600 dark:text-blue-300">{activeCount}</div>
        <div className="text-xs text-blue-600 dark:text-blue-300">Активных</div>
      </div>
      <div className="bg-yellow-50 dark:bg-yellow-900 rounded-lg p-3">
        <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-300">{newCount}</div>
        <div className="text-xs text-yellow-600 dark:text-yellow-300">Новых</div>
      </div>
      <div className="bg-green-50 dark:bg-green-900 rounded-lg p-3">
        <div className="text-2xl font-bold text-green-600 dark:text-green-300">{avgResponseTime}м</div>
        <div className="text-xs text-green-600 dark:text-green-300">Среднее</div>
      </div>
    </div>
  );
}
