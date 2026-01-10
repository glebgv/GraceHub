import { useState } from 'react';
import { Header } from '../components/common/Header';
import { OperatorList } from '../components/Operators/OperatorList';
import { AddOperatorForm } from '../components/Operators/AddOperatorForm';
import HelpdeskAPI from '../api/helpdesk';
import { useOperators } from '../hooks/useOperators';

interface OperatorsPageProps {
  api: HelpdeskAPI;
}

export default function OperatorsPage({ api }: OperatorsPageProps) {
  const { operators, loading, refresh } = useOperators(api);
  const [addLoading, setAddLoading] = useState(false);

  const handleAddOperator = async (username: string, role: string) => {
    setAddLoading(true);
    try {
      // In real implementation, resolve username to user ID
      const userId = parseInt(username) || 0;
      await api.addOperator(userId, role);
      refresh();
    } catch (error) {
      throw error;
    } finally {
      setAddLoading(false);
    }
  };

  const handleRemoveOperator = async (operatorId: number) => {
    try {
      await api.removeOperator(operatorId);
      refresh();
    } catch (error) {
      console.error('Failed to remove operator:', error);
    }
  };

  return (
    <div className="h-screen flex flex-col">
      <Header title="👥 Операторы" />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-4 space-y-4">
          <AddOperatorForm onAdd={handleAddOperator} loading={addLoading} />
          <OperatorList
            operators={operators}
            loading={loading}
            onRemove={handleRemoveOperator}
          />
        </div>
      </div>
    </div>
  );
}
