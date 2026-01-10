import { ApiClient } from './client';
import { HELPDESK_ENDPOINTS } from './endpoints';
import type { Ticket, TicketMessage } from '../types/ticket';
import type { Operator } from '../types/operator';
import type { TicketsListResponse, DashboardStats } from '../types/api';

export default class HelpdeskAPI {
  private client: ApiClient;
  private instanceId: string;

  constructor(instanceId: string, initData: string) {
    this.instanceId = instanceId;
    const baseURL = import.meta.env.VITE_API_BASE_URL || '/api';
    this.client = new ApiClient(baseURL, initData);
  }

  // ===== Tickets =====
  async getTickets(params?: {
    status?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<TicketsListResponse> {
    return this.client.get<TicketsListResponse>(
      HELPDESK_ENDPOINTS.tickets(this.instanceId),
      params
    );
  }

  async getTicketDetail(ticketId: number): Promise<Ticket> {
    return this.client.get<Ticket>(
      HELPDESK_ENDPOINTS.ticketDetail(this.instanceId, ticketId)
    );
  }

  async getTicketMessages(ticketId: number): Promise<TicketMessage[]> {
    return this.client.get<TicketMessage[]>(
      HELPDESK_ENDPOINTS.ticketMessages(this.instanceId, ticketId)
    );
  }

  async updateTicketStatus(ticketId: number, status: string): Promise<void> {
    await this.client.post(
      HELPDESK_ENDPOINTS.ticketStatus(this.instanceId, ticketId),
      { status }
    );
  }

  async assignTicket(ticketId: number, operatorId: number): Promise<void> {
    await this.client.post(
      HELPDESK_ENDPOINTS.ticketAssign(this.instanceId, ticketId),
      { operatorId }
    );
  }

  async createTopicForTicket(ticketId: number): Promise<void> {
    await this.client.post(
      HELPDESK_ENDPOINTS.ticketCreateTopic(this.instanceId, ticketId)
    );
  }

  // ===== Operators =====
  async getOperators(): Promise<Operator[]> {
    const response = await this.client.get<any>(
      HELPDESK_ENDPOINTS.operators(this.instanceId)
    );
    return Array.isArray(response) ? response : response.operators || [];
  }

  async addOperator(userId: number, role: string): Promise<void> {
    await this.client.post(
      HELPDESK_ENDPOINTS.operatorAdd(this.instanceId),
      { userid: userId, role }
    );
  }

  async removeOperator(userId: number): Promise<void> {
    await this.client.delete(
      HELPDESK_ENDPOINTS.operatorRemove(this.instanceId, userId)
    );
  }

  // ===== Stats =====
  async getDashboardStats(): Promise<DashboardStats> {
    return this.client.get<DashboardStats>(
      HELPDESK_ENDPOINTS.stats(this.instanceId)
    );
  }
}

