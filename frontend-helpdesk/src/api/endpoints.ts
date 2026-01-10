export const HELPDESK_ENDPOINTS = {
  // Tickets
  tickets: (instanceId: string) => `/instances/${instanceId}/tickets`,
  ticketDetail: (instanceId: string, ticketId: number) => `/instances/${instanceId}/tickets/${ticketId}`,
  ticketMessages: (instanceId: string, ticketId: number) => `/instances/${instanceId}/tickets/${ticketId}/messages`,
  ticketStatus: (instanceId: string, ticketId: number) => `/instances/${instanceId}/tickets/${ticketId}/status`,
  ticketAssign: (instanceId: string, ticketId: number) => `/instances/${instanceId}/tickets/${ticketId}/assign`,
  ticketCreateTopic: (instanceId: string, ticketId: number) => `/instances/${instanceId}/tickets/${ticketId}/create-topic`,
  
  // Operators
  operators: (instanceId: string) => `/instances/${instanceId}/operators`,
  operatorAdd: (instanceId: string) => `/instances/${instanceId}/operators`,
  operatorRemove: (instanceId: string, userId: number) => `/instances/${instanceId}/operators/${userId}`,
  
  // Stats
  stats: (instanceId: string) => `/instances/${instanceId}/stats/dashboard`,
};

