import { Badge } from '../common/Badge';
import { User, Clock } from 'lucide-react';
import type { Ticket } from '../../types/ticket';
import { TICKET_STATUS_EMOJI, TICKET_STATUS_LABELS } from '../../utils/constants';
import { formatDateTime } from '../../utils/time';

interface TicketHeaderProps {
  ticket: Ticket;
}

export function TicketHeader({ ticket }: TicketHeaderProps) {
  const statusEmoji = TICKET_STATUS_EMOJI[ticket.status];
  const statusLabel = TICKET_STATUS_LABELS[ticket.status];

  return (
    <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-4">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono text-lg font-bold">#{ticket.ticketid}</span>
              <Badge variant={ticket.status === 'new' ? 'warning' : ticket.status === 'closed' ? 'default' : 'info'}>
                {statusLabel}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
              <User size={16} />
              <span className="font-medium">{ticket.username || `User ${ticket.userid}`}</span>
            </div>
          </div>
          <div className="text-4xl">{statusEmoji}</div>
        </div>

        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          <div className="flex items-center gap-2">
            <Clock size={16} />
            <span>Создан: {formatDateTime(ticket.createdat)}</span>
          </div>
          {ticket.assignedusername && (
            <div className="flex items-center gap-2">
              <span>👨‍💼 Оператор: @{ticket.assignedusername}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
