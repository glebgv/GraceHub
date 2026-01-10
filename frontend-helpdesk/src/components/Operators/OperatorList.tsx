import { OperatorCard } from './OperatorCard';
import { EmptyState } from '../common/EmptyState';
import { LoadingSpinner } from '../common/LoadingSpinner';
import type { Operator } from '../../types/operator';
import { Users } from 'lucide-react';

interface OperatorListProps {
  operators: Operator[];
  loading: boolean;
  onRemove?: (operatorId: number) => void;
}

export function OperatorList({ operators, loading, onRemove }: OperatorListProps) {
  if (loading) {
    return <LoadingSpinner />;
  }

  if (operators.length === 0) {
    return <EmptyState title="Нет операторов" icon={<Users size={48} />} />;
  }

  return (
    <div className="space-y-3">
      {operators.map(operator => (
        <OperatorCard
          key={operator.userid}
          operator={operator}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
}
