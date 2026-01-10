import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Header } from '../components/common/Header';
import { TicketHeader } from '../components/TicketDetails/TicketHeader';
import { MessageList } from '../components/TicketDetails/MessageList';
import { TicketActions } from '../components/TicketDetails/TicketActions';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import HelpdeskAPI from '../api/helpdesk';
import type { Ticket, TicketMessage, TicketStatus } from '../types/ticket';

interface TicketDetailsPageProps {
  api: HelpdeskAPI;
}

export default function TicketDetailsPage({ api }: TicketDetailsPageProps) {
  const { ticketId } = useParams<{ ticketId: string }>();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<TicketMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (!ticketId) return;

    const loadTicket = async () => {
      try {
        const ticketData = await api.getTicketDetail(parseInt(ticketId));
        setTicket(ticketData);

        const messagesData = await api.getTicketMessages(parseInt(ticketId));
        setMessages(messagesData || []);
      } catch (error) {
        console.error('Failed to load ticket:', error);
      } finally {
        setLoading(false);
      }
    };

    loadTicket();
  }, [ticketId, api]);

  const handleStatusChange = async (status: TicketStatus) => {
    if (!ticket) return;

    setActionLoading(true);
    try {
      await api.updateTicketStatus(ticket.ticketid, status);
      setTicket({ ...ticket, status });
    } catch (error) {
      console.error('Failed to update status:', error);
    } finally {
      setActionLoading(false);
    }
  };

  const handleTakeTopic = async () => {
    if (!ticket) return;

    setActionLoading(true);
    try {
      await api.assignTicket(ticket.ticketid, 123456); // User ID should come from Telegram
      await api.createTopicForTicket(ticket.ticketid);
      window.Telegram?.WebApp?.showAlert('✅ Тикет взят! Топик создан в вашем чате.');
      window.Telegram?.WebApp?.close();
    } catch (error) {
      console.error('Failed to take ticket:', error);
      window.Telegram?.WebApp?.showAlert('❌ Ошибка при взятии тикета');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex flex-col">
        <Header title="Тикет" showBack />
        <div className="flex-1">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="h-screen flex flex-col">
        <Header title="Тикет" showBack />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-500">Тикет не найден</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <Header title={`#${ticket.ticketid}`} showBack />

      <TicketHeader ticket={ticket} />

      <div className="flex-1 overflow-y-auto">
        <MessageList messages={messages} loading={false} />
      </div>

      <TicketActions
        ticket={ticket}
        onStatusChange={handleStatusChange}
        onTakeTopic={handleTakeTopic}
        loading={actionLoading}
      />
    </div>
  );
}
