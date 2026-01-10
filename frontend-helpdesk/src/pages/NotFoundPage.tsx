import { Button } from '../components/common/Button';
import { useNavigate } from 'react-router-dom';

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="h-screen flex items-center justify-center bg-white dark:bg-gray-900">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-gray-200 dark:text-gray-700">404</h1>
        <p className="mt-4 text-xl text-gray-600 dark:text-gray-400">Страница не найдена</p>
        <Button
          variant="primary"
          className="mt-8"
          onClick={() => navigate('/')}
        >
          На главную
        </Button>
      </div>
    </div>
  );
}
