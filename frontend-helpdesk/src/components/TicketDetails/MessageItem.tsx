import type { TicketMessage } from '../../types/ticket';
import { formatTime } from '../../utils/time';

interface MessageItemProps {
  message: TicketMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  const isOperator = message.direction === 'operatortouser';

  return (
    <div className={`flex gap-3 ${isOperator ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
        isOperator ? 'bg-blue-100 dark:bg-blue-900 text-blue-600' : 'bg-gray-100 dark:bg-gray-800 text-gray-600'
      }`}>
        {isOperator ? '👨‍💼' : '👤'}
      </div>
      <div className={`flex-1 max-w-xs ${isOperator ? 'items-end' : 'items-start'} flex flex-col`}>
        <div className={`rounded-lg px-4 py-2 ${
          isOperator
            ? 'bg-blue-500 text-white'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
        }`}>
          <p className="text-sm break-words">{message.content}</p>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {formatTime(message.createdat)}
        </span>
      </div>
    </div>
  );
}
