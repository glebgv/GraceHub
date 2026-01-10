import { useEffect, useState, useCallback } from 'react';
import HelpdeskAPI from '../api/helpdesk';
import type { Ticket } from '../types/ticket';

export function useTickets(api: HelpdeskAPI | null, filter?: string) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = useCallback(async () => {
    if (!api) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const params: any = {};
      if (filter && filter !== 'all') {
        params.status = filter;
      }
      
      const response = await api.getTickets(params);
      setTickets(response.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tickets');
      console.error('Error loading tickets:', err);
    } finally {
      setLoading(false);
    }
  }, [api, filter]);

  useEffect(() => {
    loadTickets();
    
    // Poll every 5 seconds
    const interval = setInterval(loadTickets, 5000);
    return () => clearInterval(interval);
  }, [loadTickets]);

  return { tickets, loading, error, refresh: loadTickets };
}
