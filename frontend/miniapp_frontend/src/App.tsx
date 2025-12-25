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

        // Можно оставить авто-выбор (для последующих экранов).
        // Но первый экран всё равно будет instances.
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
    const loadSettings = async () => {
      if (!selectedInstance) {
        setChatInfo(null);
        return;
      }
      try {
        const s = await apiClient.getSettings(selectedInstance.instanceid);

        const lang = (s as any).language as string | undefined;
        if (lang && ['ru', 'en', 'es', 'hi', 'zh'].includes(lang)) {
          i18n.changeLanguage(lang);
        }

        const openchat = (s as any).openchat || {};
        const id = openchat.general_panel_chat_id ?? (s as any).generalpanelchatid ?? null;
        const username = openchat.openchat_username ?? (s as any).openchatusername ?? null;

        console.log('[App] settings for header:', { openchat, id, username, lang });

        setChatInfo({ id, username });
      } catch (e) {
        console.warn('[App] getSettings for header/lang failed', e);
        setChatInfo(null);
      }
    };

    loadSettings();
  }, [selectedInstance?.instanceid]);

  useEffect(() => {
    const loadBilling = async () => {
      if (!selectedInstance) {
        setBilling(null);
        return;
      }
      try {
        const data = await apiClient.getInstanceBilling(selectedInstance.instanceid);
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
        console.warn('[App] getInstanceBilling failed', e);
        setBilling(null);
      }
    };

    loadBilling();
  }, [selectedInstance?.instanceid]);

  const handleCreateInstanceByToken = async (token: string) => {
    try {
      setLoading(true);
      setError(null);
      setLimitMessage(null);

      console.log('[App] createInstanceByToken, preview:', token.slice(0, 10));

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

      setInstances((prev) => [...prev, normalized]);
      setSelectedInstance(normalized);
      setIsFirstLaunch(false);

      // после добавления бота логично открыть дашборд именно этого бота
      setCurrentPage('dashboard');

      if (!normalized.generalpanelchatid) {
        setShowBindHelpModal(true);
      }

      // закрываем модалку добавления на успех
      setShowAddModal(false);
    } catch (err: any) {
      console.error('[App] createInstanceByToken error', err);

      const fallback = t('firstLaunch.create_error_fallback');

      // если это ApiError со статусом 400/403 — показываем как лимит/ограничение (не уводим на error-screen)
      if (err instanceof ApiError) {
        const msg = typeof err?.message === 'string' ? err.message.trim() : '';
        const text = msg.length ? msg : fallback;

        // эвристика: любые "лимит/limit/maximum/max instances" считаем лимитным сообщением
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
            // важное: add-modal можно закрыть, чтобы пользователь не “застрял” в форме
            setShowAddModal(false);
            // возвращаем на список инстансов
            setCurrentPage('instances');
            return;
          }
        }
      }

      const message =
        typeof err?.message === 'string' && err.message.trim().length > 0
          ? err.message
          : fallback;

      setError(message);
    } finally {
      setLoading(false);
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
            setCurrentPage('instances'); // после удаления возвращаемся к списку
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

  const footerBranding = (
    <div className="app-footer">
      <a
        href="https://t.me/gracehubru"
        target="_blank"
        rel="noreferrer"
        style={{ color: 'inherit', textDecoration: 'underline' }}
      >
        GraceHub
      </a>{' '}
      {t('app.footerBrand')}
    </div>
  );

  if (loading) {
    return (
      <div className="app-container loading">
        <div className="loading-spinner" />
        <p>{t('app.loading_app')}</p>
      </div>
    );
  }

  // ВАЖНО: error-screen оставляем только для "фатальных" ошибок.
  // Лимит/ограничение показываем поверх InstancesList, не ломая UX.
  if (error) {
    return (
      <div className="app-container error">
        <div className="card">
          <p>⚠️ {error}</p>
          <p className="text-center" style={{ fontSize: 12, marginTop: 10, opacity: 0.7 }}>
            {t('app.open_from_telegram_hint')}
          </p>
        </div>
        {footerBranding}
      </div>
    );
  }

  // FirstLaunch screen
  if (
    isFirstLaunch &&
    instances.length === 0 &&
    !(currentPage === 'superadmin' && isSuperadmin)
  ) {
    return (
      <div className="app-container" style={{ justifyContent: 'flex-start' }}>
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

  // For header labels (avoid crashing if selectedInstance is null)
  const hasChat = !!chatInfo?.id;

  const planLabel =
    billing && (billing.planName || billing.planCode)
      ? billing.planName || billing.planCode
      : '—';

  const displayPlanLabel = billing?.unlimited ? t('app.tariff_private_mode') : planLabel;

  // Режим хедера: на списке инстансов показываем только тариф, внутри инстанса — только бот/чат
  const headerMode: 'list' | 'instance' =
    currentPage === 'instances' ? 'list' : 'instance';

  // ✅ Хедер показываем на InstancesList, Dashboard и Billing (чтобы на Billing был back)
  const showGlobalHeader =
    !showSuperAdminPage &&
    (currentPage === 'instances' || currentPage === 'dashboard' || currentPage === 'billing');

  // нижнее меню показываем на остальных страницах (кроме instances/superadmin/billing)
  const showBottomNav =
    !showInstancesPage &&
    !showSuperAdminPage &&
    currentPage !== 'billing' &&
    !!selectedInstance;

  return (
    <div className="app-container">
      {/* Maintenance banner can stay global */}
      {maintenance.enabled && (
        <div
          className="card"
          style={{
            borderColor: 'rgba(220, 38, 38, 0.35)',
            background: 'rgba(220, 38, 38, 0.08)',
            marginBottom: 12,
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
            {t('app.maintenance_title', 'Технические работы')}
          </div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            {maintenance.message || t('app.maintenance_message', 'Сервис временно недоступен.')}
          </div>
        </div>
      )}

      {showGlobalHeader && (
        <header className="app-header">
          {/* ===== InstancesList header: left tariff-card, right tariffs-button ===== */}
          {headerMode === 'list' && (
            <div className="header-row">
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
                        <span className="tariff-label">До:</span>
                        <span className="tariff-value">
                          {billing ? new Date(billing.periodEnd).toLocaleDateString() : '—'}
                        </span>
                      </div>
                      <div className="tariff-row">
                        <span className="tariff-label">Осталось дней:</span>
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
            </div>
          )}

          {/* ===== Dashboard/Billing header: bot/chat + back button ===== */}
          {headerMode === 'instance' && selectedInstance && (
            <div className="header-content">
              <div style={{ minWidth: 0 }}>
                <h1>{selectedInstance.botname || t('app.default_title')}</h1>

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
                  <div
                    style={{
                      marginTop: 4,
                      fontSize: 11,
                      color: 'var(--tg-color-success, #16a34a)',
                    }}
                  >
                    {t('app.chat_connected', { id: chatInfo?.id })}
                  </div>
                ) : (
                  <div
                    style={{
                      marginTop: 4,
                      fontSize: 11,
                      color: 'var(--tg-color-error, #dc2626)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      flexWrap: 'wrap',
                    }}
                  >
                    {t('app.chat_not_connected')}
                    <button
                      type="button"
                      onClick={() => setShowBindHelpModal(true)}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        padding: 0,
                        margin: 0,
                        fontSize: 11,
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        color: 'inherit',
                      }}
                    >
                      {t('app.chat_not_connected_more')}
                    </button>
                  </div>
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

      <main className="main-content">
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

        {currentPage === 'dashboard' && selectedInstance && (
          <Dashboard instanceId={selectedInstance.instanceid} />
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

      {showBindHelpModal && (
        <div className="modal-backdrop" onClick={() => setShowBindHelpModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">{t('bindHelp.title')}</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowBindHelpModal(false)}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: 8 }}>{t('bindHelp.paragraph1')}</p>
              <p style={{ marginBottom: 8 }}>{t('bindHelp.paragraph2')}</p>
              <p style={{ marginBottom: 0 }}>
                {t('bindHelp.paragraph3', {
                  bot_username: selectedInstance?.botusername,
                })}
              </p>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setShowBindHelpModal(false)}
              >
                {t('bindHelp.ok')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
