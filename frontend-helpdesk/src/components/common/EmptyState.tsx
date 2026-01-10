import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
}

export function EmptyState({ title, description, icon = <Inbox size={48} /> }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-gray-400 dark:text-gray-600 mb-4">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">{title}</h3>
      {description && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 max-w-sm">{description}</p>
      )}
    </div>
  );
}
