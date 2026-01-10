import { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useTelegram } from './hooks/useTelegram';
import HelpdeskAPI from './api/helpdesk';

// Pages
import LoadingPage from './pages/LoadingPage';
import NotFoundPage from './pages/NotFoundPage';
import DashboardPage from './pages/DashboardPage';
import TicketsPage from './pages/TicketsPage';
import TicketDetailsPage from './pages/TicketDetailsPage';
import OperatorsPage from './pages/OperatorsPage';

export default function App() {
  const { user, initData, isReady, colorScheme } = useTelegram();
  const [api, setApi] = useState<HelpdeskAPI | null>(null);
  const [instanceId, setInstanceId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;

    // Get instance ID from URL
    const params = new URLSearchParams(window.location.search);
    const instance = params.get('instance');

    if (!instance) {
      setError('Instance ID не найден в URL');
      return;
    }

    setInstanceId(instance);
    
    // Initialize API
    try {
      const helpdeskApi = new HelpdeskAPI(instance, initData || '');
      setApi(helpdeskApi);
    } catch (err) {
      setError('Ошибка инициализации API');
      console.error('API initialization error:', err);
    }
  }, [isReady, initData]);

  if (!isReady) {
    return <LoadingPage />;
  }

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center bg-red-50 dark:bg-red-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-800 dark:text-red-200 mb-2">Ошибка</h1>
          <p className="text-red-700 dark:text-red-300">{error}</p>
        </div>
      </div>
    );
  }

  if (!api || !user) {
    return <LoadingPage />;
  }

  return (
    <Router basename="/helpdesk">
      <div className={colorScheme === 'dark' ? 'dark' : ''}>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage api={api} />} />
            <Route path="/tickets" element={<TicketsPage api={api} />} />
            <Route path="/tickets/:ticketId" element={<TicketDetailsPage api={api} />} />
            <Route path="/operators" element={<OperatorsPage api={api} />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}
