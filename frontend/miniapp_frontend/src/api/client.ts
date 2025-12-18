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

// --- Billing invoices ---

// NB: оставляем твой текущий контракт snake_case, чтобы не перепахивать Billing.tsx.
export type PaymentMethod = 'telegram_stars' | 'ton' | 'yookassa';

export interface CreateInvoiceRequest {
  plan_code: string;
  periods: number;
  payment_method?: PaymentMethod;
}

export interface CreateInvoiceResponse {
  invoice_id: number;
  invoice_link: string;
  // опционально: backend может вернуть ещё поля (не ломаем типизацию)
  amount_minor_units?: number;
  amount_ton?: number;
  currency?: string;
}

export interface TonInvoiceStatusResponse {
  invoice_id: number;
  status: 'pending' | 'paid' | 'failed';
  tx_hash?: string | null;
  period_applied: boolean;
}

export interface YooKassaStatusResponse {
  invoice_id: number;
  status: string; // pending/succeeded/canceled/waiting_for_capture/...
  payment_id?: string | null;
  period_applied: boolean;
}

// --- Platform settings (platform_settings table) ---

// GET /api/platform/settings -> { key: "miniapp_public", value: {...} }
export interface PlatformSettingsResponse {
  key: string;
  value: Record<string, any>;
}

// POST /api/platform/settings/{key} body: { value: {...} }
export interface PlatformSettingUpsertRequest {
  value: Record<string, any>;
}

export interface SimpleStatusResponse {
  status: string;
}

// --- Manage (superadmin) ---
export interface ManageHealthResponse {
  status: string;
}

/**
 * То, что хранится в platform_settings["miniapp_public"].
 * Важно: single-tenant режим в бекенде читается из singleTenant.allowedUserIds. [file:52]
 */
export interface MiniappPublicSettings {
  singleTenant: {
    enabled: boolean;
    allowedUserIds: number[];
    // legacy (старое поле, может встречаться в БД после миграций/ручных правок)
    ownerTelegramId?: number | null;
  };

  superadmins: number[];

  payments: {
    enabled: {
      telegramStars: boolean;
      ton: boolean;
      yookassa: boolean;
    };
    ton: {
      network: 'testnet' | 'mainnet';
      walletAddress: string;
      apiBaseUrl: string;
      apiKey: string;
      checkDelaySeconds: number;
      confirmationsRequired: number;
      pricePerPeriodLite: number;
      pricePerPeriodPro: number;
      pricePerPeriodEnterprise: number;
    };
    yookassa: {
      shopId: string;
      secretKey: string;
      returnUrl: string;
      testMode: boolean;
      priceRubLite: number;
      priceRubPro: number;
      priceRubEnterprise: number;
    };
  };

  instanceDefaults: {
    antifloodMaxUserMessagesPerMinute: number;
    workerMaxFileMb: number;
    maxInstancesPerUser: number;
  };
}

function normalizeIds(list: any): number[] {
  if (!Array.isArray(list)) return [];
  const out = new Set<number>();
  for (const x of list) {
    const n = Number(x);
    if (Number.isFinite(n) && n > 0) out.add(n);
  }
  return Array.from(out).sort((a, b) => a - b);
}

/**
 * Нормализация miniapp_public:
 * - гарантирует наличие singleTenant.allowedUserIds
 * - мигрирует старое singleTenant.ownerTelegramId -> allowedUserIds [file:52]
 */
function normalizeMiniappPublicSettings(raw: any): MiniappPublicSettings {
  const v = raw || {};
  const st = v?.singleTenant || {};

  let allowed = normalizeIds(st?.allowedUserIds);
  if (allowed.length === 0 && st?.ownerTelegramId !== null && st?.ownerTelegramId !== undefined) {
    allowed = normalizeIds([st.ownerTelegramId]);
  }

  return {
    ...v,
    singleTenant: {
      ...st,
      enabled: !!st?.enabled,
      allowedUserIds: allowed,
      // ownerTelegramId оставляем как legacy-поле (не используем в UI, но не ломаем старые данные)
      ownerTelegramId: st?.ownerTelegramId === undefined ? undefined : st?.ownerTelegramId,
    },
  } as MiniappPublicSettings;
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

  private async request<T>(method: string, path: string, body?: any): Promise<T> {
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

    const options: RequestInit = { method, headers };

    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }

    console.log('[ApiClient] request >>>', { method, url, headers, body });

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
      const detail = (json && (json.detail || json.message || json.error)) || `Ошибка ${response.status}`;
      throw new Error(detail);
    }

    return json as T;
  }

  // === Manage (superadmin) ===
  async getManageHealth(): Promise<ManageHealthResponse> {
    return this.request<ManageHealthResponse>('GET', '/manage/health');
  }

  // === Auth ===
  async authTelegram(req: AuthRequest): Promise<AuthResponse> {
    console.log('[ApiClient] authTelegram payload:', req, {
      url: `${this.baseUrl}/api/auth/telegram`,
    });

    return this.request<AuthResponse>('POST', '/api/auth/telegram', {
      initData: req.initData,
      start_param: req.start_param ?? undefined,
    });
  }

  async resolveInstance(payload: ResolveInstanceRequest): Promise<ResolveInstanceResponse> {
    console.log('[ApiClient] resolveInstance payload:', payload, {
      url: `${this.baseUrl}/api/resolve_instance`,
    });

    return this.request<ResolveInstanceResponse>('POST', '/api/resolve_instance', payload);
  }

  async getMe() {
    return this.request('GET', '/api/me');
  }

  // === Instances ===
  async getInstances() {
    return this.request('GET', '/api/instances');
  }

  async createInstanceByToken(payload: CreateInstanceRequest): Promise<InstanceDto> {
    console.log('[ApiClient] createInstanceByToken payload:', {
      hasToken: !!payload.token,
      tokenPreview: payload.token?.slice(0, 10),
    });

    return this.request<InstanceDto>('POST', '/api/instances', { token: payload.token });
  }

  async deleteInstance(instanceId: string): Promise<void> {
    return this.request<void>('DELETE', `/api/instances/${instanceId}`);
  }

  async getStats(instanceId: string, days: number = 30) {
    return this.request('GET', `/api/instances/${instanceId}/stats?days=${days}`);
  }

  async getSettings(instanceId: string) {
    return this.request('GET', `/api/instances/${instanceId}/settings`);
  }

  async updateSettings(instanceId: string, settings: any) {
    return this.request('POST', `/api/instances/${instanceId}/settings`, settings);
  }

  async getTickets(instanceId: string, status?: string, search?: string, limit: number = 20, offset: number = 0) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (search) params.append('search', search);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());

    return this.request('GET', `/api/instances/${instanceId}/tickets?${params.toString()}`);
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
    return this.request('DELETE', `/api/instances/${instanceId}/operators/${userId}`);
  }

  // === Billing ===
  async getInstanceBilling(instanceId: string) {
    return this.request('GET', `/api/instances/${instanceId}/billing`);
  }

  async getSaasPlans(): Promise<SaasPlanDTO[]> {
    return this.request<SaasPlanDTO[]>('GET', '/api/saas/plans');
  }

  async createBillingInvoice(instanceId: string, payload: CreateInvoiceRequest): Promise<CreateInvoiceResponse> {
    return this.request<CreateInvoiceResponse>('POST', `/api/instances/${instanceId}/billing/create_invoice`, payload);
  }

  // TON invoice status polling
  async getTonInvoiceStatus(invoiceId: number): Promise<TonInvoiceStatusResponse> {
    const params = new URLSearchParams();
    params.append('invoice_id', String(invoiceId));

    return this.request<TonInvoiceStatusResponse>('GET', `/api/billing/ton/status?${params.toString()}`);
  }

  // YooKassa invoice status polling
  async getYooKassaInvoiceStatus(invoiceId: number): Promise<YooKassaStatusResponse> {
    const params = new URLSearchParams();
    params.append('invoice_id', String(invoiceId));

    return this.request<YooKassaStatusResponse>('GET', `/api/billing/yookassa/status?${params.toString()}`);
  }

  // === Platform settings ===

  /**
   * GET /api/platform/settings
   * Backend возвращает ключ "miniapp_public" и его value. [file:52]
   */
  async getPlatformSettings(): Promise<PlatformSettingsResponse> {
    return this.request<PlatformSettingsResponse>('GET', '/api/platform/settings');
  }

  /**
   * POST /api/platform/settings/{key}
   * Только superadmin (backend проверяет роли). [file:52]
   */
  async setPlatformSetting(key: string, value: Record<string, any>): Promise<SimpleStatusResponse> {
    const payload: PlatformSettingUpsertRequest = { value };
    return this.request<SimpleStatusResponse>('POST', `/api/platform/settings/${encodeURIComponent(key)}`, payload);
  }

  // --- Convenience wrappers for SuperAdmin page (miniapp_public) ---
  async getMiniappPublicSettings(): Promise<MiniappPublicSettings> {
    const res = await this.getPlatformSettings();
    return normalizeMiniappPublicSettings(res?.value || {});
  }

  async setMiniappPublicSettings(value: MiniappPublicSettings): Promise<SimpleStatusResponse> {
    // перед сохранением гарантируем нормальный массив id
    const normalized = normalizeMiniappPublicSettings(value);
    // важно: ownerTelegramId не нужен; если он там остался — можно убрать, чтобы не плодить legacy
    const cleaned: any = {
      ...normalized,
      singleTenant: {
        enabled: !!normalized.singleTenant.enabled,
        allowedUserIds: normalizeIds(normalized.singleTenant.allowedUserIds),
      },
    };
    return this.setPlatformSetting('miniapp_public', cleaned);
  }
}

export const apiClient = new ApiClient();
