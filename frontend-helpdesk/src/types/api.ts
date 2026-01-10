export interface ApiResponse<T> {
  data?: T;
  error?: string;
  message?: string;
  status?: string;
}

export interface TicketsListResponse {
  items: Ticket[];
  total: number;
}

export interface DashboardStats {
  activeTickets: number;
  newTickets: number;
  inProgressTickets: number;
  closedToday: number;
  avgResponseTime: number;
  needAttention: number;
}

export interface OperatorsResponse {
  operators: Operator[];
}
