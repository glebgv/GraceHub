import { AlertCircle, X } from 'lucide-react';
import { useState } from 'react';

interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  const [isVisible, setIsVisible] = useState(true);

  const handleDismiss = () => {
    setIsVisible(false);
    onDismiss?.();
  };

  if (!isVisible) return null;

  return (
    <div className="bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-700 rounded-lg p-4 flex gap-3 items-start">
      <AlertCircle size={20} className="text-red-600 dark:text-red-300 flex-shrink-0 mt-0.5" />
      <p className="text-red-800 dark:text-red-100 flex-1 text-sm">{message}</p>
      <button
        onClick={handleDismiss}
        className="text-red-600 dark:text-red-300 hover:text-red-700 dark:hover:text-red-200"
      >
        <X size={18} />
      </button>
    </div>
  );
}
