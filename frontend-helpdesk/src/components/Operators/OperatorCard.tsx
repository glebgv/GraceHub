import { Trash2, User } from 'lucide-react';
import { Button } from '../common/Button';
import type { Operator } from '../../types/operator';

interface OperatorCardProps {
  operator: Operator;
  onRemove?: (operatorId: number) => void;
}

export function OperatorCard({ operator, onRemove }: OperatorCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-white">
            <User size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium">@{operator.username || `User ${operator.userid}`}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {operator.role === 'owner' ? 'Владелец' : 'Оператор'}
            </div>
          </div>
        </div>
        {operator.role !== 'owner' && onRemove && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onRemove(operator.userid)}
          >
            <Trash2 size={16} />
          </Button>
        )}
      </div>

      {operator.activetickets !== undefined && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 grid grid-cols-2 gap-2 text-xs">
          <div>
            <div className="text-gray-500 dark:text-gray-400">Активных</div>
            <div className="font-bold">{operator.activetickets}</div>
          </div>
          <div>
            <div className="text-gray-500 dark:text-gray-400">Закрыто сегодня</div>
            <div className="font-bold">{operator.closedtoday || 0}</div>
          </div>
        </div>
      )}
    </div>
  );
}
