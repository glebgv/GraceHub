export type TicketStatus = 'new' | 'inprogress' | 'answered' | 'closed' | 'spam';
export type MessageDirection = 'usertoopenchat' | 'operatortouser';

export interface Ticket {
  ticketid: number;
  userid: number;
  username?: string;
  status: TicketStatus;
  createdat: string;
  lastusermsgat?: string;
  lastadminreplyat?: string;
  openchattopicid?: number;
  assignedusername?: string;
  assigneduserid?: number;
  messagecount?: number;
}

export interface TicketMessage {
  id: number;
  content: string;
  direction: MessageDirection;
  createdat: string;
  userid: number;
  username?: string;
}

export interface TicketDetailResponse {
  ticket: Ticket;
  messages?: TicketMessage[];
}
