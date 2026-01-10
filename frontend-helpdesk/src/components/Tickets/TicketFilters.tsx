import { cn } from '../../utils/classNames';

interface TicketFiltersProps {
  activeFilter: string;
  onFilterChange: (filter: string) => void;
}

const filters = [
  { value: 'all', label: 'Все' },
  { value: 'new', label: 'Новые' },
  { value: 'inprogress', label: 'В работе' },
  { value: 'answered', label: 'Отвеченные' },
  { value: 'closed', label: 'Закрытые' },
];

export function TicketFilters({ activeFilter, onFilterChange }: TicketFiltersProps) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4">
      {filters.map(filter => (
        <button
          key={filter.value}
          onClick={() => onFilterChange(filter.value)}
          className={cn(
            'px-4 py-2 rounded-full whitespace-nowrap font-medium transition text-sm',
            activeFilter === filter.value
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
          )}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
