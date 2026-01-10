import { LoadingSpinner } from '../components/common/LoadingSpinner';

export default function LoadingPage() {
  return (
    <div className="h-screen flex items-center justify-center bg-white dark:bg-gray-900">
      <div className="text-center">
        <LoadingSpinner />
        <p className="mt-4 text-gray-600 dark:text-gray-400">Инициализация...</p>
      </div>
    </div>
  );
}
