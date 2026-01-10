import { MessageItem } from './MessageItem';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { EmptyState } from '../common/EmptyState';
import type { TicketMessage } from '../../types/ticket';
import { MessageSquare } from 'lucide-react';

interface MessageListProps {
  messages: TicketMessage[];
  loading: boolean;
}

export function MessageList({ messages, loading }: MessageListProps) {
  if (loading) {
    return <LoadingSpinner />;
  }

  if (messages.length === 0) {
    return <EmptyState title="Нет сообщений" icon={<MessageSquare size={48} />} />;
  }

  return (
    <div className="space-y-4 p-4">
      {messages.map(message => (
        <MessageItem key={message.id} message={message} />
      ))}
    </div>
  );
}
