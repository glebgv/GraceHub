// src/api/client.ts

/**
 * API клиент для общения с бекендом mini app
 *
 * Исправления/улучшения:
 * - Добавлен ApiError (статус + тело ответа), чтобы UI мог различать ошибки по коду.
 * - В request() добавлен accept: application/json и более надёжный разбор ошибок.
 * - Небольшая нормализация snake_case/camelCase в DTO там, где UI уже ожидает snake_case.
 * - PaymentMethod приведён к значениям, которые реально ждёт backend: telegramstars/ton/yookassa/stripe.
 *
 * FIX (важно): добавлен Stripe в MiniappPublicSettings.payments.enabled и нормализацию,
 * иначе enabled.stripe вырезался при сохранении из SuperAdmin.
 *
 * NEW (оферта):
 * - Добавлено поле MiniappPublicSettings.offer (enabled + url)
 * - Добавлены методы getOfferStatus / postOfferDecision для FirstLaunch-геийтинга
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

export type PaymentMethod = 'telegram_stars' | 'ton' | 'yookassa' | 'stripe';

// NB: оставляем твой текущий контракт snake_case, чтобы не перепахивать Billing.tsx.
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
  session_id?: string;
}

export interface UserSubscription {
  plan_code: string;
  plan_name: string;
  period_start: string;
  period_end: string;
  days_left: number;
  instances_limit: number;
  instances_created: number;
  unlimited: boolean;
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

/**
 * Stripe invoice status polling (snake_case для UI)
 * Backend: StripeInvoiceStatusResponseBaseModel:
 * - invoiceid
 * - status: pending/succeeded/failed/canceled
 * - sessionid
 * - paymentintentid
 * - periodapplied
 */
export interface StripeInvoiceStatusResponse {
  invoice_id: number;
  status: 'pending' | 'succeeded' | 'failed' | 'canceled';
  session_id?: string | null;
  payment_intent_id?: string | null;
  period_applied: boolean;
}

// --- Offer (публичная оферта) ---

export interface OfferStatusResponse {
  enabled: boolean;
  url: string;
  accepted: boolean;
  acceptedAt?: string | null;
}

export interface OfferDecisionRequest {
  accepted: boolean;
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
 * Важно: single-tenant режим в бекенде читается из singleTenant.allowedUserIds.
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
      stripe: boolean; // FIX: было потеряно
    };

    // prices for Telegram Stars
    telegramStars: {
      priceStarsLite: number;
      priceStarsPro: number;
      priceStarsEnterprise: number;
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

    stripe: {
      secretKey: string;
      publishableKey: string;
      webhookSecret: string;
      currency: string;
      priceUsdLite: number;
      priceUsdPro: number;
      priceUsdEnterprise: number;

      // если добавишь на бэке/в UI — просто раскомментируй:
      // successUrl?: string;
      // cancelUrl?: string;
      // testMode?: boolean;
    };
  };

  // NEW: публичная оферта (платформенная настройка)
  offer?: {
    enabled: boolean;
    url: string;
  };

  instanceDefaults: {
    antifloodMaxUserMessagesPerMinute: number;
    workerMaxFileMb: number;
    maxInstancesPerUser: number;
  };
}

export interface PlatformMetrics {
  total_clients: number;
  active_bots: number;
  monthly_tickets: number;
  paid_subscriptions: number;
}

// --- User settings ---
export interface UserSettingsResponse {
  language?: string;
  // другие настройки пользователя могут быть добавлены здесь
}

export interface SaveLanguageRequest {
  language: string;
}

/**
 * Ошибка API с кодом HTTP и телом ответа (если оно было).
 * Удобно для UI: можно делать проверку e.status === 400 и e.message.includes(...).
 */
export class ApiError extends Error {
  status: number;
  body: any;
  url?: string;

  constructor(message: string, status: number, body?: any, url?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.url = url;
  }
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

function safeNumber(v: any, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/**
 * Нормализация miniapp_public:
 * - гарантирует наличие singleTenant.allowedUserIds
 * - мигрирует старое singleTenant.ownerTelegramId -> allowedUserIds
 * - гарантирует наличие payments.* секций и enabled-флагов
 * - NEW: гарантирует offer.enabled/url
 */
function normalizeMiniappPublicSettings(raw: any): MiniappPublicSettings {
  const v = raw || {};
  const st = v?.singleTenant || {};
  const p = v?.payments || {};
  const ts = p?.telegramStars || {};
  const ton = p?.ton || {};
  const yk = p?.yookassa || {};
  const sp = p?.stripe || {};
  const offer = v?.offer || {};

  let allowed = normalizeIds(st?.allowedUserIds);
  if (allowed.length === 0 && st?.ownerTelegramId !== null && st?.ownerTelegramId !== undefined) {
    allowed = normalizeIds([st.ownerTelegramId]);
  }

  // дефолты — можно синхронизировать с SuperAdmin.tsx
  const defaultStarsLite = 100;
  const defaultStarsPro = 300;
  const defaultStarsEnt = 999;

  const defaultStripeCurrency = 'usd';
  const defaultUsdLite = 4.99;
  const defaultUsdPro = 9.99;
  const defaultUsdEnt = 29.99;

  return {
    ...v,
    singleTenant: {
      ...st,
      enabled: !!st?.enabled,
      allowedUserIds: allowed,
      // ownerTelegramId оставляем как legacy-поле (не используем в UI, но не ломаем старые данные)
      ownerTelegramId: st?.ownerTelegramId === undefined ? undefined : st?.ownerTelegramId,
    },
    superadmins: Array.isArray(v?.superadmins) ? normalizeIds(v.superadmins) : [],
    payments: {
      ...p,
      enabled: {
        telegramStars: !!p?.enabled?.telegramStars,
        ton: !!p?.enabled?.ton,
        yookassa: !!p?.enabled?.yookassa,
        stripe: !!p?.enabled?.stripe, // FIX: раньше вырезалось
      },
      telegramStars: {
        priceStarsLite: safeNumber(ts?.priceStarsLite, defaultStarsLite),
        priceStarsPro: safeNumber(ts?.priceStarsPro, defaultStarsPro),
        priceStarsEnterprise: safeNumber(ts?.priceStarsEnterprise, defaultStarsEnt),
      },
      ton: {
        network: ton?.network === 'mainnet' ? 'mainnet' : 'testnet',
        walletAddress: String(ton?.walletAddress ?? ''),
        apiBaseUrl: String(ton?.apiBaseUrl ?? ''),
        apiKey: String(ton?.apiKey ?? ''),
        checkDelaySeconds: safeNumber(ton?.checkDelaySeconds, 5),
        confirmationsRequired: safeNumber(ton?.confirmationsRequired, 1),
        pricePerPeriodLite: safeNumber(ton?.pricePerPeriodLite, 0.5),
        pricePerPeriodPro: safeNumber(ton?.pricePerPeriodPro, 2.0),
        pricePerPeriodEnterprise: safeNumber(ton?.pricePerPeriodEnterprise, 5.0),
      },
      yookassa: {
        shopId: String(yk?.shopId ?? ''),
        secretKey: String(yk?.secretKey ?? ''),
        returnUrl: String(yk?.returnUrl ?? ''),
        testMode: yk?.testMode !== undefined ? !!yk.testMode : true,
        priceRubLite: safeNumber(yk?.priceRubLite, 199),
        priceRubPro: safeNumber(yk?.priceRubPro, 499),
        priceRubEnterprise: safeNumber(yk?.priceRubEnterprise, 1999),
      },
      stripe: {
        secretKey: String(sp?.secretKey ?? ''),
        publishableKey: String(sp?.publishableKey ?? ''),
        webhookSecret: String(sp?.webhookSecret ?? ''),
        currency: String(sp?.currency ?? defaultStripeCurrency).toLowerCase(),
        priceUsdLite: safeNumber(sp?.priceUsdLite, defaultUsdLite),
        priceUsdPro: safeNumber(sp?.priceUsdPro, defaultUsdPro),
        priceUsdEnterprise: safeNumber(sp?.priceUsdEnterprise, defaultUsdEnt),
      },
    },
    offer: {
      enabled: !!offer?.enabled,
      url: String(offer?.url ?? ''),
    },
    instanceDefaults: {
      antifloodMaxUserMessagesPerMinute: safeNumber(
        v?.instanceDefaults?.antifloodMaxUserMessagesPerMinute,
        20,
      ),
      workerMaxFileMb: safeNumber(v?.instanceDefaults?.workerMaxFileMb, 10),
      maxInstancesPerUser: safeNumber(v?.instanceDefaults?.maxInstancesPerUser, 3),
    },
  };
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

  async getSuperadminMetrics(): Promise<PlatformMetrics> {
    return this.request<PlatformMetrics>('GET', '/api/superadmin/metrics');
  }

  private async request<T>(method: string, path: string, body?: any): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
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

    let response: Response;
    try {
      response = await fetch(url, options);
    } catch (e: any) {
      // network / CORS / DNS / etc.
      throw new ApiError(e?.message || 'Network error', 0, undefined, url);
    }

    const text = await response.text().catch(() => '');
    let json: any = null;

    try {
      json = text ? JSON.parse(text) : null;
    } catch {
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
      // FastAPI обычно возвращает {detail: "..."}
      const detail =
        (json && (json.detail ?? json.message ?? json.error)) ||
        (text ? text.slice(0, 200) : '') ||
        `Ошибка ${response.status}`;

      throw new ApiError(String(detail), response.status, json ?? text, url);
    }

    // На случай 204 No Content
    if (response.status === 204) {
      return undefined as T;
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

  // === User Settings ===
  async getUserSettings(): Promise<UserSettingsResponse> {
    return this.request<UserSettingsResponse>('GET', '/api/user/settings');
  }

  async saveUserLanguage(language: string): Promise<SimpleStatusResponse> {
    const payload: SaveLanguageRequest = { language };
    return this.request<SimpleStatusResponse>('POST', '/api/user/settings/language', payload);
  }

  // === Offer (публичная оферта) ===
  async getOfferStatus(): Promise<OfferStatusResponse> {
    return this.request<OfferStatusResponse>('GET', '/api/offer/status');
  }

  async postOfferDecision(accepted: boolean): Promise<{ status: string; accepted?: boolean }> {
    const payload: OfferDecisionRequest = { accepted: !!accepted };
    return this.request('POST', '/api/offer/decision', payload);
  }

  // === Instances ===
  async getInstances(): Promise<InstanceDto[]> {
    return this.request<InstanceDto[]>('GET', '/api/instances');
  }

  async getSuperadminClients(
    offset: number = 0,
    limit: number = 50,
    search?: string
  ): Promise<{ clients: Array<any>; total: number }> {
    const params = new URLSearchParams();
    params.append('offset', String(offset));
    params.append('limit', String(limit));
    if (search) params.append('search', search.trim());

    return this.request<{ clients: Array<any>; total: number }>(
      'GET',
      `/api/superadmin/clients?${params.toString()}`
    );
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

  // Метод
  async getUserSubscription(): Promise<UserSubscription> {
    return this.request<UserSubscription>('GET', '/api/user/subscription');
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

  // Stripe invoice status polling
  async getStripeInvoiceStatus(invoiceId: number): Promise<StripeInvoiceStatusResponse> {
    const raw = await this.request<any>('GET', `/api/invoices/stripe/${invoiceId}/status`); // endpoint есть на бэке
    // нормализуем в snake_case, чтобы UI был единообразным
    return {
      invoice_id: Number(raw?.invoiceid ?? raw?.invoice_id ?? invoiceId),
      status: String(raw?.status ?? 'pending') as any,
      session_id: raw?.sessionid ?? raw?.session_id ?? null,
      payment_intent_id: raw?.paymentintentid ?? raw?.payment_intent_id ?? null,
      period_applied: !!(raw?.periodapplied ?? raw?.period_applied),
    };
  }

  // === Platform settings ===

  /**
   * GET /api/platform/settings
   * Backend возвращает ключ "miniapp_public" и его value.
   */
  async getPlatformSettings(): Promise<PlatformSettingsResponse> {
    return this.request<PlatformSettingsResponse>('GET', '/api/platform/settings');
  }

  /**
   * POST /api/platform/settings/{key}
   * Только superadmin (backend проверяет роли).
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
    // перед сохранением нормализуем (важно: теперь НЕ вырезает enabled.stripe)
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

  async getPlatformMetrics(): Promise<PlatformMetrics> {
    return this.request<PlatformMetrics>('GET', '/api/platform/metrics');
  }
}

export const apiClient = new ApiClient();