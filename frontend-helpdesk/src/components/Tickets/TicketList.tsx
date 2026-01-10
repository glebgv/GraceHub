import { TicketCard } from './TicketCard';
import { EmptyState } from '../common/EmptyState';
import { LoadingSpinner } from '../common/LoadingSpinner';
import type { Ticket } from '../../types/ticket';
import { Inbox } from 'lucide-react';

interface TicketListProps {
  tickets: Ticket[];
  loading: boolean;
}

export function TicketList({ tickets, loading }: TicketListProps) {
  if (loading) {
    return <LoadingSpinner />;
  }

  if (tickets.length === 0) {
    return <EmptyState title="Нет тикетов" description="Тикеты появятся здесь" icon={<Inbox size={48} />} />;
  }

  return (
    <div className="space-y-3">
      {tickets.map(ticket => (
        <TicketCard key={ticket.ticketid} ticket={ticket} />
      ))}
    </div>
  );
}
