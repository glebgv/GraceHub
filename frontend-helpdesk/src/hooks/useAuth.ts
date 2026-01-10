import { useEffect, useState } from 'react';

interface User {
  id: number;
  username?: string;
  firstName?: string;
}

export function useAuth(initData: string) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!initData) {
      setLoading(false);
      return;
    }

    // In production, verify initData on backend
    // For now, we trust it from Telegram
    setIsAuthenticated(true);
    setLoading(false);
  }, [initData]);

  return { isAuthenticated, user, loading };
}
