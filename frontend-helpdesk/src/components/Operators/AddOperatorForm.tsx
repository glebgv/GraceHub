import { useState } from 'react';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import { UserPlus } from 'lucide-react';

interface AddOperatorFormProps {
  onAdd: (username: string, role: string) => Promise<void>;
  loading?: boolean;
}

export function AddOperatorForm({ onAdd, loading = false }: AddOperatorFormProps) {
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('operator');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError('Введите username оператора');
      return;
    }

    try {
      await onAdd(username, role);
      setUsername('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка при добавлении оператора');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
      <h3 className="font-bold mb-4 flex items-center gap-2">
        <UserPlus size={20} />
        Добавить оператора
      </h3>

      {error && (
        <div className="bg-red-50 dark:bg-red-900 text-red-700 dark:text-red-200 text-sm rounded-lg p-3 mb-4">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <Input
          placeholder="@username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          disabled={loading}
        />

        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="w-full px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:border-blue-500"
        >
          <option value="operator">Оператор</option>
          <option value="viewer">Просмотр</option>
        </select>

        <Button
          type="submit"
          variant="primary"
          className="w-full"
          loading={loading}
        >
          Добавить
        </Button>
      </div>
    </form>
  );
}
