// src/api/client.ts

/**
 * API клиент для общения с бекендом mini app
 */

export interface AuthRequest {
  initData: string;
  start_param?: string;
}

export interface AuthResponse {
  token: string;
  user: any;
  default_instance_id?: string;
}

export interface ResolveInstanceRequest {
  instance_id?: string;
  admin_id?: number;
}

export interface ResolveInstanceResponse {
  instance_id: string | null;
  bot_username?: string | null;
  bot_name?: string | null;
  role?: string | null;
  created_at?: string | null;
  openchat_username?: string | null;
  general_panel_chat_id?: number | null;
  link_forbidden?: boolean;
}

// создание инстанса (аналог /add_bot в мастер‑боте)
export interface CreateInstanceRequest {
  token: string;
}

// DTO инстанса, который возвращает backend
export interface InstanceDto {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
}

export interface SaasPlanDTO {
  planCode: string;
  planName: string;
  periodDays: number;
  ticketsLimit: number;
  priceStars: number;
  productCode: string | null;
}

class ApiClient {
  private token: string | null = null;
  private baseUrl: string;
  private initData: string | null = null;

  constructor(baseUrl: string = '') {
    // baseUrl типа "https://gracehub.ru"
    this.baseUrl = baseUrl || window.location.origin;
    console.log('[ApiClient] baseUrl =', this.baseUrl);
  }

  setToken(token: string | null) {
    this.token = token;
    console.log('[ApiClient] setToken', !!token);
  }

  clearToken() {
    this.token = null;
    console.log('[ApiClient] clearToken');
  }

  /**
   * Сырой initData от Telegram WebApp.
   * Прокидывается в заголовок X-Telegram-Init-Data,
   * чтобы backend мог валидировать запросы независимо от сессии.
   */
  setInitData(initData: string) {
    this.initData = initData;
    console.log('[ApiClient] setInitData', {
      length: initData?.length,
      preview: initData?.slice(0, 60),
    });
  }

  private async request<T>(
    method: string,
    path: string,
    body?: any,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (this.initData) {
      headers['X-Telegram-Init-Data'] = this.initData;
    }

    const options: RequestInit = {
      method,
      headers,
    };

    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }

    console.log('[ApiClient] request >>>', {
      method,
      url,
      headers,
      body,
    });

    const response = await fetch(url, options);

    const text = await response.text().catch(() => '');
    let json: any = null;

    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }

    console.log('[ApiClient] response <<<', {
      status: response.status,
      ok: response.ok,
      url: response.url,
      body: json,
      rawText: text?.slice(0, 500),
    });

    if (!response.ok) {
      // backend для единой логики может вернуть detail, message или errors
      const detail =
        (json && (json.detail || json.message || json.error)) ||
        `Ошибка ${response.status}`;
      throw new Error(detail);
    }

    return json as T;
  }

  async authTelegram(req: AuthRequest): Promise<AuthResponse> {
    console.log('[ApiClient] authTelegram payload:', req, {
      url: `${this.baseUrl}/api/auth/telegram`,
    });

    return this.request<AuthResponse>('POST', '/api/auth/telegram', {
      initData: req.initData, // ключ в camelCase, как в Pydantic alias
      start_param: req.start_param ?? undefined,
    });
  }

  async resolveInstance(
    payload: ResolveInstanceRequest,
  ): Promise<ResolveInstanceResponse> {
    console.log('[ApiClient] resolveInstance payload:', payload, {
      url: `${this.baseUrl}/api/resolve_instance`,
    });

    return this.request<ResolveInstanceResponse>(
      'POST',
      '/api/resolve_instance',
      payload,
    );
  }

  async getMe() {
    return this.request('GET', '/api/me');
  }

  async getInstances() {
    return this.request('GET', '/api/instances');
  }

  async createInstanceByToken(
    payload: CreateInstanceRequest,
  ): Promise<InstanceDto> {
    console.log('[ApiClient] createInstanceByToken payload:', {
      hasToken: !!payload.token,
      tokenPreview: payload.token?.slice(0, 10),
    });

    return this.request<InstanceDto>(
      'POST',
      '/api/instances',
      { token: payload.token },
    );
  }

  async deleteInstance(instanceId: string): Promise<void> {
    return this.request<void>('DELETE', `/api/instances/${instanceId}`);
  }

  async getStats(instanceId: string, days: number = 30) {
    return this.request(
      'GET',
      `/api/instances/${instanceId}/stats?days=${days}`,
    );
  }

  async getSettings(instanceId: string) {
    return this.request('GET', `/api/instances/${instanceId}/settings`);
  }

  async updateSettings(instanceId: string, settings: any) {
    return this.request(
      'POST',
      `/api/instances/${instanceId}/settings`,
      settings,
    );
  }

  async getTickets(
    instanceId: string,
    status?: string,
    search?: string,
    limit: number = 20,
    offset: number = 0,
  ) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (search) params.append('search', search);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());

    return this.request(
      'GET',
      `/api/instances/${instanceId}/tickets?${params.toString()}`,
    );
  }

  async getOperators(instanceId: string) {
    return this.request('GET', `/api/instances/${instanceId}/operators`);
  }

  async addOperator(instanceId: string, userId: number, role: string) {
    return this.request('POST', `/api/instances/${instanceId}/operators`, {
      user_id: userId,
      role,
    });
  }

  async removeOperator(instanceId: string, userId: number) {
    return this.request(
      'DELETE',
      `/api/instances/${instanceId}/operators/${userId}`,
    );
  }

  // === Billing ===

  async getInstanceBilling(instanceId: string) {
    return this.request(
      'GET',
      `/api/instances/${instanceId}/billing`,
    );
  }

  async getSaasPlans(): Promise<SaasPlanDTO[]> {
    return this.request<SaasPlanDTO[]>(
      'GET',
      '/api/saas/plans',
    );
  }
}

export const apiClient = new ApiClient();
