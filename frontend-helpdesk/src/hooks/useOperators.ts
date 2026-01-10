import { useEffect, useState, useCallback } from 'react';
import HelpdeskAPI from '../api/helpdesk';
import type { Operator } from '../types/operator';

export function useOperators(api: HelpdeskAPI | null) {
  const [operators, setOperators] = useState<Operator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadOperators = useCallback(async () => {
    if (!api) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.getOperators();
      setOperators(response || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load operators');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadOperators();
  }, [loadOperators]);

  return { operators, loading, error, refresh: loadOperators };
}

