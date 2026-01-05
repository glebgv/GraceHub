// src/App.tsx
import React, { useEffect, useMemo, useState } from 'react';
import './App.css';
import Dashboard from './pages/Dashboard';
import InstancesList from './pages/InstancesList';
import Tickets from './pages/Tickets';
import Operators from './pages/Operators';
import Settings from './pages/Settings';
import Billing from './pages/Billing';
import SuperAdmin from './pages/SuperAdmin';
import { apiClient, ApiError } from './api/client';
import FirstLaunch from './pages/FirstLaunch';
import { useTranslation } from 'react-i18next';
import i18n from './i18n';
import AddBotModal from './components/AddBotModal';
import 'flag-icons/css/flag-icons.min.css';
import { Drawer } from 'vaul';

interface AppProps {
  instanceIdFromUrl: string | null;
  adminIdFromUrl: string | null;
  currentUserId: number | null;
  initDataRaw: string | null;
}

type Page =
  | 'instances'
  | 'dashboard'
  | 'tickets'
  | 'operators'
  | 'settings'
  | 'billing'
  | 'superadmin';

type Instance = {
  instanceid: string;
  botusername: string;
  botname: string;
  role: string;
  openchatusername?: string | null;
  generalpanelchatid?: number | null;
};

type BillingState = {
  planCode: string;
  planName: string;
  periodStart: string;
  periodEnd: string;
  daysLeft: number;
  ticketsUsed: number;
  ticketsLimit: number;
  overLimit: boolean;
  unlimited: boolean;
};

type PlatformSettings = Record<string, any>;

const App: React.FC<AppProps> = ({
  instanceIdFromUrl,
  adminIdFromUrl,
  currentUserId,
  initDataRaw,
}) => {
  const { t } = useTranslation();

  const [user, setUser] = useState<any | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [selectedInstance, setSelectedInstance] = useState<Instance | null>(null);

  // ✅ Always start from InstancesList screen
  const [currentPage, setCurrentPage] = useState<Page>('instances');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isFirstLaunch, setIsFirstLaunch] = useState(false);

  const [chatInfo, setChatInfo] = useState<{
    id: number | null;
    username: string | null;
  } | null>(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [showBindHelpModal, setShowBindHelpModal] = useState(false);

  const [billing, setBilling] = useState<BillingState | null>(null);

  // NEW: platform settings (platform_settings["miniapp_public"])
  const [platformSettings, setPlatformSettings] = useState<PlatformSettings>({});
  const [platformSettingsLoaded, setPlatformSettingsLoaded] = useState(false);

  // NEW: отдельное состояние под "лимит инстансов", чтобы не уводить в глобальный error-screen
  const [limitMessage, setLimitMessage] = useState<string | null>(null);

  // ✨ NEW: page animation trigger
  const [pageAnim, setPageAnim] = useState(false);

  // ✨ NEW: состояние создания инстанса для показа скелетона Dashboard
  const [isCreatingInstance, setIsCreatingInstance] = useState(false);

  const [instanceDataLoading, setInstanceDataLoading] = useState(false);

  const isSuperadmin = useMemo(() => {
    const roles = user?.roles || [];
    return Array.isArray(roles) && roles.includes('superadmin');
  }, [user]);

  // ---- derived helpers from platform settings ----
  const maintenance = useMemo(() => {
    const ps = platformSettings || {};
    const enabled = !!ps.maintenance_enabled;
    const message = (ps.maintenance_message as string | undefined) || '';
    return { enabled, message };
  }, [platformSettings]);

  // ✨ NEW: page transition animation
  useEffect(() => {
    setPageAnim(true);
    const timeoutId = window.setTimeout(() => setPageAnim(false), 260);
    return () => window.clearTimeout(timeoutId);
  }, [currentPage]);

  useEffect(() => {
    const initApp = async () => {
      console.log('[App.initApp] start', {
        instanceIdFromUrl,
        adminIdFromUrl,
        currentUserId,
        hasInitDataRaw: !!initDataRaw,
        initDataPreview: initDataRaw?.slice(0, 80),
      });

      try {
        setLoading(true);
        setError(null);

        const initData = initDataRaw || '';

        if (!initData) {
          console.warn('[App.initApp] initData отсутствует или пуста');
          setError(t('app.open_from_telegram'));
          setLoading(false);
          return;
        }

        apiClient.setInitData(initData);

        const startParam = '';

        console.log('[App.initApp] calling authTelegram', { startParam });

        const authResponse = await apiClient.authTelegram({
          initData,
          start_param: startParam,
        });

        console.log('[App.initApp] authResponse:', {
          user: authResponse.user,
          default_instance_id: authResponse.default_instance_id,
          instancesCount: authResponse.user?.instances?.length,
        });

        apiClient.setToken(authResponse.token);
        setUser(authResponse.user);

        let resolvedInstance: Instance | null = null;
        let linkForbidden = false;

        try {
          const payload: any = {};

          if (instanceIdFromUrl) {
            payload.instance_id = instanceIdFromUrl;
          }

          if (adminIdFromUrl) {
            const adminNum = Number(adminIdFromUrl);
            if (!Number.isNaN(adminNum)) {
              payload.admin_id = adminNum;
            }
          }

          console.log('[App.initApp] resolveInstance payload:', payload);

          if (payload.instance_id || payload.admin_id) {
            const resolveResp = await apiClient.resolveInstance(payload);

            console.log('[App.initApp] resolveInstance response:', resolveResp);

            if (resolveResp.link_forbidden) {
              linkForbidden = true;
            } else if (resolveResp.instance_id) {
              resolvedInstance = {
                instanceid: resolveResp.instance_id,
                botusername: resolveResp.bot_username ?? '',
                botname: resolveResp.bot_name ?? '',
                role: resolveResp.role ?? 'owner',
                openchatusername: resolveResp.openchat_username ?? null,
                generalpanelchatid: resolveResp.general_panel_chat_id ?? null,
              };
            } else {
              console.warn('[App.initApp] resolveInstance returned no instance_id', resolveResp);
            }
          } else {
            console.log('[App.initApp] no instance_id/admin_id in payload, skip resolveInstance');
          }
        } catch (e: any) {
          console.warn(
            '[App.initApp] resolve_instance error (продолжаем без него):',
            e?.message || e,
          );
        }

        if (linkForbidden) {
          setSelectedInstance(null);
          setError(t('app.owner_only'));
          setLoading(false);
          return;
        }

        console.log('[App.initApp] fallback instance selection', {
          instancesCount: authResponse.user.instances?.length,
        });

        const userInstancesRaw = authResponse.user.instances || [];
        const normalizedList: Instance[] = userInstancesRaw.map((src: any): Instance => ({
          instanceid: src.instanceid || src.instance_id,
          botusername: src.botusername || src.bot_username || '',
          botname: src.botname || src.bot_name || '',
          role: src.role || 'owner',
          openchatusername: src.openchatusername || src.openchat_username || null,
          generalpanelchatid: src.generalpanelchatid || src.general_panel_chat_id || null,
        }));

        setInstances(normalizedList);

        if (normalizedList.length === 0) {
          console.log(
            '[App.initApp] first launch: no instances for this user, show FirstLaunch screen',
          );
          setIsFirstLaunch(true);
          setSelectedInstance(null);
          setCurrentPage('instances');
          setLoading(false);
          return;
        }

        if (resolvedInstance) {
          setSelectedInstance(resolvedInstance);
        } else {
          setSelectedInstance((prev) => {
            if (prev) return prev;

            const defId = authResponse.default_instance_id;
            if (defId) {
              const fromList = normalizedList.find((i) => i.instanceid === defId);
              if (fromList) return fromList;
            }

            return normalizedList[0] ?? null;
          });
        }

        // ✅ Always land on InstancesList after init
        setCurrentPage('instances');

        setLoading(false);
        console.log('[App.initApp] done (resolvedInstance) =', resolvedInstance);
      } catch (err: any) {
        console.error('[App.initApp] FATAL Ошибка инициализации:', {
          message: err?.message,
          stack: err?.stack,
        });

        if (
          typeof err?.message === 'string' &&
          err.message.includes('панель доступна только владельцу')
        ) {
          setError(t('app.owner_only'));
        } else {
          setError(t('app.open_from_telegram'));
        }

        setLoading(false);
      }
    };

    initApp();
  }, [instanceIdFromUrl, adminIdFromUrl, initDataRaw, currentUserId, t]);

  // NEW: load platform settings once token is set (after initApp)
  useEffect(() => {
    const loadPlatformSettings = async () => {
      if (!user) return;
      if (platformSettingsLoaded) return;

      try {
        const res = await apiClient.getPlatformSettings();
        setPlatformSettings(res?.value || {});
      } catch (e) {
        console.warn('[App] getPlatformSettings failed (ignored)', e);
        setPlatformSettings({});
      } finally {
        setPlatformSettingsLoaded(true);
      }
    };

    loadPlatformSettings();
  }, [user, platformSettingsLoaded]);

  useEffect(() => {
    if (!selectedInstance) {
      setChatInfo(null);
      setBilling(null);
      setInstanceDataLoading(false);
      return;
    }

    setChatInfo(null);
    setBilling(null);
    setInstanceDataLoading(true);

    const loadAll = async () => {
      try {
        const [s, data] = await Promise.all([
          apiClient.getSettings(selectedInstance.instanceid),
          apiClient.getInstanceBilling(selectedInstance.instanceid),
        ]);

        const lang = (s as any).language as string | undefined;
        if (lang && ['ru', 'en', 'es', 'hi', 'zh'].includes(lang)) {
          i18n.changeLanguage(lang);
        }

        const openchat = (s as any).openchat || {};
        const id = openchat.general_panel_chat_id ?? (s as any).generalpanelchatid ?? null;
        const username = openchat.openchat_username ?? (s as any).openchatusername ?? null;

        console.log('[App] settings for header:', { openchat, id, username, lang });

        setChatInfo({ id, username });

        setBilling({
          planCode: data.plan_code,
          planName: data.plan_name,
          periodStart: data.period_start,
          periodEnd: data.period_end,
          daysLeft: data.days_left,
          ticketsUsed: data.tickets_used,
          ticketsLimit: data.tickets_limit,
          overLimit: data.over_limit,
          unlimited: !!data.unlimited,
        });
      } catch (e) {
        console.warn('[App] load instance data (settings/billing) failed', e);
        setChatInfo(null);
        setBilling(null);
      } finally {
        setInstanceDataLoading(false);
      }
    };

    loadAll();
  }, [selectedInstance?.instanceid]);

  const handleCreateInstanceByToken = async (token: string) => {
    try {
      // ✅ НЕ используем глобальный loading - вместо этого используем isCreatingInstance
      setError(null);
      setLimitMessage(null);
      setIsCreatingInstance(true);

      console.log('[App] createInstanceByToken, preview:', token.slice(0, 10));

      // ✅ Создаём временный инстанс для немедленного показа Dashboard со скелетоном
      const tempInstance: Instance = {
        instanceid: 'temp-loading',
        botusername: '',
        botname: 'Загрузка...',
        role: 'owner',
        openchatusername: null,
        generalpanelchatid: null,
      };

      // ✅ Сразу переключаемся на Dashboard - там будет показан скелетон
      setSelectedInstance(tempInstance);
      setIsFirstLaunch(false);
      setCurrentPage('dashboard');
      setShowAddModal(false);

      // Теперь отправляем запрос к API
      const created = await apiClient.createInstanceByToken({ token });

      console.log('[App] created instance', created);

      const normalized: Instance = {
        instanceid: created.instanceid,
        botusername: created.botusername,
        botname: created.botname,
        role: created.role || 'owner',
        openchatusername: (created as any).openchatusername ?? null,
        generalpanelchatid: (created as any).generalpanelchatid ?? null,
      };

      // ✅ Обновляем список и выбранный инстанс реальными данными
      setInstances((prev) => [...prev, normalized]);
      setSelectedInstance(normalized);

      if (!normalized.generalpanelchatid) {
        setShowBindHelpModal(true);
      }
    } catch (err: any) {
      console.error('[App] createInstanceByToken error', err);

      const fallback = t('firstLaunch.create_error_fallback');

      if (err instanceof ApiError) {
        const msg = typeof err?.message === 'string' ? err.message.trim() : '';
        const text = msg.length ? msg : fallback;

        const lower = text.toLowerCase();
        const looksLikeLimit =
          lower.includes('лимит') ||
          lower.includes('limit') ||
          lower.includes('maximum') ||
          lower.includes('max') ||
          lower.includes('instances');

        if (err.status === 400 || err.status === 403) {
          if (looksLikeLimit) {
            setLimitMessage(text);
            // ✅ При ошибке лимита возвращаемся на instances
            setIsFirstLaunch(true);
            setCurrentPage('instances');
            setSelectedInstance(null);
            return;
          }
        }
      }

      const message =
        typeof err?.message === 'string' && err.message.trim().length > 0
          ? err.message
          : fallback;

      setError(message);
      // ✅ При любой другой ошибке тоже возвращаемся
      setIsFirstLaunch(true);
      setCurrentPage('instances');
      setSelectedInstance(null);
    } finally {
      setIsCreatingInstance(false);
    }
  };

  const handleDeleteInstance = async (inst: Instance) => {
    try {
      console.log('[App] delete instance', inst);
      setLoading(true);
      setError(null);

      await apiClient.deleteInstance(inst.instanceid);

      setInstances((prev) => {
        const filtered = prev.filter((i) => i.instanceid !== inst.instanceid);

        if (selectedInstance?.instanceid === inst.instanceid) {
          if (filtered.length > 0) {
            setSelectedInstance(filtered[0]);
            setCurrentPage('instances');
          } else {
            setSelectedInstance(null);
            setIsFirstLaunch(true);
            setCurrentPage('instances');
          }
        }

        return filtered;
      });
    } catch (err: any) {
      console.error('[App] deleteInstance error', err);
      const fallback = t('firstLaunch.create_error_fallback');
      const message =
        typeof err?.message === 'string' && err.message.trim().length > 0
          ? err.message
          : fallback;
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenBot = () => {
    if (!selectedInstance?.botusername) return;
    const botUrl = `https://t.me/${selectedInstance.botusername}?start=help`;
    window.open(botUrl, '_blank');
  };

  const footerBranding = (
    <div className="app-footer">
      <a
        href="https://github.com/glebgv/GraceHub/"
        target="_blank"
        rel="noreferrer"
        className="footer-link"
      >
        GraceHub
      </a>{' '}
      {t('app.footerBrand')}
    </div>
  );

  if (loading) {
    return (
      <div className="app-container app-loading">
        {/* Пустой или минималистичный placeholder */}
      </div>
    );
  }

  if (error) {
    return (
      <div className="app-container app-error">
        <div className="card">
          <p className="error-message">⚠️ {error}</p>
          <p className="error-hint">{t('app.open_from_telegram_hint')}</p>
        </div>
        {footerBranding}
      </div>
    );
  }

  if (
    isFirstLaunch &&
    instances.length === 0 &&
    !(currentPage === 'superadmin' && isSuperadmin)
  ) {
    return (
      <div className="app-container app-first-launch">
        <FirstLaunch
          onAddBotClick={handleCreateInstanceByToken}
          instanceId={null}
          isSuperadmin={isSuperadmin}
          onOpenAdmin={() => {
            setIsFirstLaunch(false);
            setCurrentPage('superadmin');
          }}
        />
        {footerBranding}
      </div>
    );
  }

  const showInstancesPage = currentPage === 'instances';
  const showSuperAdminPage = currentPage === 'superadmin';

  const hasChat = !!chatInfo?.id;

  const planLabel =
    billing && (billing.planName || billing.planCode)
      ? billing.planName || billing.planCode
      : '—';

  const displayPlanLabel = billing?.unlimited ? t('app.tariff_private_mode') : planLabel;

  const headerMode: 'list' | 'instance' = currentPage === 'instances' ? 'list' : 'instance';

  const showGlobalHeader =
    !showSuperAdminPage &&
    (currentPage === 'instances' || currentPage === 'dashboard' || currentPage === 'billing');

  const showBottomNav =
    !showInstancesPage &&
    !showSuperAdminPage &&
    currentPage !== 'billing' &&
    !!selectedInstance;

  const isHeaderLoading = isCreatingInstance || instanceDataLoading;

  return (
    <div className="app-container">
      {maintenance.enabled && (
        <div className="card maintenance-banner">
          <div className="maintenance-title">
            {t('app.maintenance_title', 'Технические работы')}
          </div>
          <div className="maintenance-message">
            {maintenance.message || t('app.maintenance_message', 'Сервис временно недоступен.')}
          </div>
        </div>
      )}

      {showGlobalHeader && (
        <header className="app-header">
          {headerMode === 'list' && (
            <div className="header-row">
              {isHeaderLoading ? (
                <>
                  {/* Скелетон для левой части (tariff-card) */}
                  <div className="header-left">
                    <div className="tariff-card">
                      <div className="tariff-row">
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '4rem',
                            borderRadius: '4px',
                            marginRight: '0.5rem'
                          }}
                        ></span>
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '6rem',
                            borderRadius: '4px'
                          }}
                        ></span>
                      </div>
                      <div className="tariff-row">
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '5rem',
                            borderRadius: '4px',
                            marginRight: '0.5rem'
                          }}
                        ></span>
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '7rem',
                            borderRadius: '4px'
                          }}
                        ></span>
                      </div>
                      <div className="tariff-row">
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '6rem',
                            borderRadius: '4px',
                            marginRight: '0.5rem'
                          }}
                        ></span>
                        <span 
                          className="skeleton animate-pulse"
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#e5e7eb',
                            minHeight: '1rem',
                            width: '3rem',
                            borderRadius: '4px'
                          }}
                        ></span>
                      </div>
                    </div>
                  </div>

                  {/* Скелетон для правой части (кнопка Биллинг) */}
                  <div className="header-right">
                    <div 
                      className="skeleton animate-pulse"
                      style={{
                        display: 'block',
                        backgroundColor: '#e5e7eb',
                        minHeight: '2.5rem',
                        width: '7rem',
                        borderRadius: '999px'
                      }}
                    ></div>
                  </div>
                </>
              ) : (
                <>
                  <div className="header-left">
                    <div className="tariff-card">
                      <div className="tariff-row">
                        <span className="tariff-label">{t('app.tariff_label')}:</span>
                        <span className="tariff-value">
                          {billing
                            ? billing.unlimited
                              ? `${displayPlanLabel} · ∞`
                              : displayPlanLabel
                            : '—'}
                        </span>
                      </div>

                      {!billing?.unlimited && (
                        <>
                          <div className="tariff-row">
                            <span className="tariff-label">{t('billing.valid_until')}:</span>
                            <span className="tariff-value">
                              {billing ? new Date(billing.periodEnd).toLocaleDateString() : '—'}
                            </span>
                          </div>
                          <div className="tariff-row">
                            <span className="tariff-label">{t('billing.days_left')}:</span>
                            <span className="tariff-value">{billing ? billing.daysLeft : '—'}</span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="header-right">
                    <button
                      type="button"
                      className={`header-link ${currentPage === 'billing' ? 'active' : ''}`}
                      onClick={() => setCurrentPage('billing')}
                      aria-label={t('nav.billing')}
                    >
                      <span className="header-link-icon" aria-hidden="true">
                        💳
                      </span>
                      <span className="header-link-text">{t('nav.billing')}</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {headerMode === 'instance' && selectedInstance && (
            <div className="header-content">
              <div className="header-info">
                {isHeaderLoading ? (
                  <>
                    {/* Скелетон для заголовка (botname) */}
                    <h1 className="header-title">
                      <div 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '1.5rem',
                          width: '10rem',
                          borderRadius: '4px'
                        }}
                      ></div>
                    </h1>
                    {/* Скелетон для instance-badge */}
                    <div className="instance-badge" style={{ border: 'none', background: 'transparent' }}>
                      <div 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '1rem',
                          width: '9rem',
                          borderRadius: '4px'
                        }}
                      ></div>
                    </div>
                    {/* Скелетон для chat-status */}
                    <div className="chat-status">
                      <div 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '1rem',
                          width: '12rem',
                          borderRadius: '4px'
                        }}
                      ></div>
                    </div>
                  </>
                ) : (
                  <>
                    <h1 className="header-title">{selectedInstance.botname || t('app.default_title')}</h1>
                    <div className="instance-badge">
                      {selectedInstance.botusername ? (
                        <>
                          <a
                            href={`https://t.me/${selectedInstance.botusername}`}
                            target="_blank"
                            rel="noreferrer"
                            className="bot-username-link"
                          >
                            @{selectedInstance.botusername}
                          </a>
                          {' · '}
                          {selectedInstance.role}
                        </>
                      ) : (
                        selectedInstance.role
                      )}
                    </div>
                    {hasChat ? (
                      <div className="chat-status chat-connected">
                        {t('app.chat_connected', { id: chatInfo?.id })}
                      </div>
                    ) : (
                      <div className="chat-status chat-not-connected">
                        {t('app.chat_not_connected')}
                        <button
                          type="button"
                          onClick={() => setShowBindHelpModal(true)}
                          className="chat-help-link"
                        >
                          {t('app.chat_not_connected_more')}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
              <button
                type="button"
                className="btn-back"
                onClick={() => setCurrentPage('instances')}
                aria-label={t('common.back', 'Назад')}
                title={t('common.back', 'Назад')}
              >
                ←
              </button>
            </div>
          )}
        </header>
      )}

      <main className={`main-content ${pageAnim ? 'gh-page-animating' : ''}`}>
        {currentPage === 'instances' && (
          <InstancesList
            instances={instances}
            onSelect={(inst) => {
              setSelectedInstance(inst);
              setCurrentPage('dashboard');
            }}
            onAddBotClick={() => {
              setLimitMessage(null);
              setShowAddModal(true);
            }}
            onDeleteInstance={handleDeleteInstance}
            onOpenSuperAdmin={isSuperadmin ? () => setCurrentPage('superadmin') : undefined}
            limitMessage={limitMessage}
            onDismissLimitMessage={() => setLimitMessage(null)}
            onGoHome={() => {
              setShowAddModal(false);
              setCurrentPage('instances');
            }}
          />
        )}

        {/* ✅ Показываем Dashboard если есть selectedInstance ИЛИ идёт создание инстанса */}
        {currentPage === 'dashboard' && (isCreatingInstance || selectedInstance) && (
          <Dashboard instanceId={selectedInstance?.instanceid || ''} />
        )}

        {currentPage === 'tickets' && selectedInstance && (
          <Tickets instanceId={selectedInstance.instanceid} />
        )}

        {currentPage === 'operators' && selectedInstance && selectedInstance.role === 'owner' && (
          <Operators instanceId={selectedInstance.instanceid} />
        )}

        {currentPage === 'settings' && selectedInstance && selectedInstance.role === 'owner' && (
          <Settings instanceId={selectedInstance.instanceid} />
        )}

        {currentPage === 'billing' && selectedInstance && (
          <Billing instanceId={selectedInstance.instanceid} />
        )}

        {currentPage === 'superadmin' && isSuperadmin && (
          <SuperAdmin
            onBack={() => {
              setCurrentPage('instances');
            }}
          />
        )}
      </main>

      {footerBranding}

      {showBottomNav && (
        <nav className="app-nav">
          <div className="app-nav-inner">
            <button
              className={`nav-button ${currentPage === 'dashboard' ? 'active' : ''}`}
              onClick={() => setCurrentPage('dashboard')}
            >
              <span className="nav-icon">📊</span>
              <span className="nav-label">{t('nav.dashboard')}</span>
            </button>

            <button
              className={`nav-button ${currentPage === 'tickets' ? 'active' : ''}`}
              onClick={() => setCurrentPage('tickets')}
            >
              <span className="nav-icon">🎫</span>
              <span className="nav-label">{t('nav.tickets')}</span>
            </button>

            {selectedInstance?.role === 'owner' && (
              <>
                <button
                  className={`nav-button ${currentPage === 'operators' ? 'active' : ''}`}
                  onClick={() => setCurrentPage('operators')}
                >
                  <span className="nav-icon">👥</span>
                  <span className="nav-label">{t('nav.operators')}</span>
                </button>

                <button
                  className={`nav-button ${currentPage === 'settings' ? 'active' : ''}`}
                  onClick={() => setCurrentPage('settings')}
                >
                  <span className="nav-icon">⚙️</span>
                  <span className="nav-label">{t('nav.settings')}</span>
                </button>
              </>
            )}
          </div>
        </nav>
      )}

      {showAddModal && (
        <AddBotModal
          onClose={() => setShowAddModal(false)}
          onSubmitToken={handleCreateInstanceByToken}
        />
      )}

      {/* bindHelp Bottom Sheet */}
      <Drawer.Root
        open={showBindHelpModal}
        onOpenChange={(open) => {
          if (!open) setShowBindHelpModal(false);
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content">
            <div className="drawer-body">
              <Drawer.Handle className="drawer-handle" />

              <div className="drawer-header">
                <h3 className="drawer-title">{t('bindHelp.title')}</h3>
                <button
                  type="button"
                  onClick={() => setShowBindHelpModal(false)}
                  className="drawer-close-btn"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>

              <div className="bind-help-content">
                <p className="bind-help-paragraph">{t('bindHelp.paragraph1')}</p>
                <p className="bind-help-paragraph">{t('bindHelp.paragraph2')}</p>
                <p className="bind-help-paragraph bind-help-paragraph-last">
                  {t('bindHelp.paragraph3', {
                    bot_username: selectedInstance?.botusername,
                  })}
                </p>
              </div>

              <div className="drawer-footer">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={handleOpenBot}
                >
                  {t('bindHelp.openBot', 'Открыть бот')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={() => setShowBindHelpModal(false)}
                >
                  {t('bindHelp.ok')}
                </button>
              </div>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </div>
  );
};

export default App;
