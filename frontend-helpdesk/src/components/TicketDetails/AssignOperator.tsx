import { useState } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import type { Operator } from '../../types/operator';

interface AssignOperatorProps {
  isOpen: boolean;
  onClose: () => void;
  operators: Operator[];
  onAssign: (operatorId: number) => void;
  loading?: boolean;
}

export function AssignOperator({ isOpen, onClose, operators, onAssign, loading = false }: AssignOperatorProps) {
  const [selectedOperator, setSelectedOperator] = useState<number | null>(null);

  const handleAssign = () => {
    if (selectedOperator) {
      onAssign(selectedOperator);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      title="Назначить оператора"
      onClose={onClose}
      footer={
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose} className="flex-1">
            Отмена
          </Button>
          <Button
            variant="primary"
            onClick={handleAssign}
            disabled={!selectedOperator || loading}
            loading={loading}
            className="flex-1"
          >
            Назначить
          </Button>
        </div>
      }
    >
      <div className="space-y-2">
        {operators.map(op => (
          <button
            key={op.userid}
            onClick={() => setSelectedOperator(op.userid)}
            className={`w-full text-left p-3 rounded-lg border-2 transition ${
              selectedOperator === op.userid
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900'
                : 'border-gray-200 dark:border-gray-700 hover:border-blue-300'
            }`}
          >
            <div className="font-medium">@{op.username || `User ${op.userid}`}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {op.role === 'owner' ? 'Владелец' : 'Оператор'}
            </div>
          </button>
        ))}
      </div>
    </Modal>
  );
}
