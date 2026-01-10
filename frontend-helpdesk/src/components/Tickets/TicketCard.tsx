import { Clock, MessageSquare, User, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Ticket } from '../../types/ticket';
import { Badge } from '../common/Badge';
import { TICKET_STATUS_EMOJI, TICKET_STATUS_LABELS } from '../../utils/constants';
import { formatRelativeTime } from '../../utils/time';

interface TicketCardProps {
  ticket: Ticket;
}

export function TicketCard({ ticket }: TicketCardProps) {
  const statusEmoji = TICKET_STATUS_EMOJI[ticket.status];
  const statusLabel = TICKET_STATUS_LABELS[ticket.status];

  return (
    <Link
      to={`/tickets/${ticket.ticketid}`}
      className="block bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 transition"
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">#{ticket.ticketid}</span>
            <Badge variant={ticket.status === 'new' ? 'warning' : ticket.status === 'closed' ? 'default' : 'info'}>
              {statusLabel}
            </Badge>
          </div>
          <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
            <User size={14} />
            <span className="truncate">{ticket.username || `User ${ticket.userid}`}</span>
          </div>
        </div>
        <div className="text-2xl flex-shrink-0">{statusEmoji}</div>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mb-3">
        <span className="flex items-center gap-1">
          <Clock size={14} />
          {formatRelativeTime(ticket.createdat)}
        </span>
        {ticket.messagecount && (
          <span className="flex items-center gap-1">
            <MessageSquare size={14} />
            {ticket.messagecount}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between">
        {ticket.assignedusername && (
          <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-gray-700 dark:text-gray-300">
            → @{ticket.assignedusername}
          </span>
        )}
        <ChevronRight size={18} className="text-gray-400" />
      </div>
    </Link>
  );
}
