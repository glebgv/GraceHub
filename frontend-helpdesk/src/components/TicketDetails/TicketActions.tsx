import { Button } from '../common/Button';
import { Menu, Check, Archive, AlertTriangle } from 'lucide-react';
import type { Ticket, TicketStatus } from '../../types/ticket';
import { useState } from 'react';

interface TicketActionsProps {
  ticket: Ticket;
  onStatusChange: (status: TicketStatus) => void;
  onTakeTopic: () => void;
  loading?: boolean;
}

export function TicketActions({ ticket, onStatusChange, onTakeTopic, loading = false }: TicketActionsProps) {
  const [showMenu, setShowMenu] = useState(false);

  if (ticket.status === 'closed') {
    return <div />;
  }

  return (
    <div className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 p-4 sticky bottom-0">
      <div className="max-w-2xl mx-auto flex gap-2">
        {ticket.status === 'new' && (
          <>
            <Button
              variant="primary"
              size="lg"
              className="flex-1"
              onClick={onTakeTopic}
              loading={loading}
            >
              🎫 Взять себе
            </Button>
            <Button
              variant="ghost"
              size="lg"
              onClick={() => onStatusChange('spam')}
            >
              <AlertTriangle size={18} />
            </Button>
          </>
        )}

        {ticket.status === 'inprogress' && (
          <>
            <Button
              variant="primary"
              size="lg"
              className="flex-1"
              onClick={() => onStatusChange('answered')}
            >
              <Check size={18} />
              Отправить ответ
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => onStatusChange('spam')}
            >
              <AlertTriangle size={18} />
            </Button>
          </>
        )}

        {ticket.status === 'answered' && (
          <>
            <Button
              variant="secondary"
              size="lg"
              className="flex-1"
              onClick={() => onStatusChange('inprogress')}
            >
              Переоткрыть
            </Button>
            <Button
              variant="primary"
              size="lg"
              onClick={() => onStatusChange('closed')}
            >
              <Archive size={18} />
              Закрыть
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
