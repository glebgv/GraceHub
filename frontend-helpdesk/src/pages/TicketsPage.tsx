import { useState } from 'react';
import { Header } from '../components/common/Header';
import { TicketFilters } from '../components/Tickets/TicketFilters';
import { TicketSearch } from '../components/Tickets/TicketSearch';
import { TicketList } from '../components/Tickets/TicketList';
import { ErrorBanner } from '../components/common/ErrorBanner';
import HelpdeskAPI from '../api/helpdesk';
import { useTickets } from '../hooks/useTickets';

interface TicketsPageProps {
  api: HelpdeskAPI;
}

export default function TicketsPage({ api }: TicketsPageProps) {
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState<string>('');
  const { tickets, loading, error } = useTickets(api, filter);

  const filteredTickets = search
    ? tickets.filter(t => {
        const query = search.toLowerCase();
        return (
          t.username?.toLowerCase().includes(query) ||
          t.userid.toString().includes(query) ||
          `#${t.ticketid}`.includes(query)
        );
      })
    : tickets;

  return (
    <div className="h-screen flex flex-col">
      <Header title="🎫 Тикеты" />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-4">
          {error && (
            <ErrorBanner
              message={error}
              onDismiss={() => {}}
            />
          )}

          <TicketSearch
            onSearch={setSearch}
            onClear={() => setSearch('')}
          />

          <TicketFilters
            activeFilter={filter}
            onFilterChange={setFilter}
          />

          <div className="mt-4">
            <TicketList tickets={filteredTickets} loading={loading} />
          </div>
        </div>
      </div>
    </div>
  );
}
