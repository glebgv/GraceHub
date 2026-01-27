// src/App.tsx
// creator GraceHub Tg: @Gribson_Micro
import React, { useEffect, useMemo, useState, useRef } from 'react';
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


  //  Always start from InstancesList screen
  const [currentPage, setCurrentPage] = useState<Page>('instances');


  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);


  const [isFirstLaunch, setIsFirstLaunch] = useState(false);


  const [chatInfo, setChatInfo] = useState<{
    id: number | null;
    username: string | null;
  } | null>(null);

  const [deletingInstanceId, setDeletingInstanceId] = useState<string | null>(null);

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


  // NEW: состояние для фоновых ошибок при удалении
  const [backgroundError, setBackgroundError] = useState<string | null>(null);

  // NEW: флаг, показывающий, что идет процесс удаления (для предотвращения загрузки данных)
  const [isDeleting, setIsDeleting] = useState(false);


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


  const hasInitialized = useRef(false);

  useEffect(() => {
    // Выполняем инициализацию только один раз
    if (hasInitialized.current) return;
    hasInitialized.current = true;

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

        const initData = initDataRaw;
        if (!initData) {
          console.warn('[App.initApp] initData missing');
          setError(t('app.openFromTelegram'));
          setLoading(false);
          return;
        }

        apiClient.setInitData(initData);
        const startParam = '';
        console.log('[App.initApp] calling authTelegram', { startParam });
        const authResponse = await apiClient.authTelegram({
          initData,
          startparam: startParam,
        });


        console.log('[App.initApp] authResponse:', {
          user: authResponse.user,
          default_instance_id: authResponse.defaultinstanceid,
          instancesCount: authResponse.user?.instances?.length,
        });
        apiClient.setToken(authResponse.token);
        setUser(authResponse.user);

        let resolvedInstance: Instance | null = null;
        let linkForbidden = false;

        try {
          const payload: any = {};

          if (instanceIdFromUrl) {
            payload.instanceid = instanceIdFromUrl;
          }

          if (adminIdFromUrl) {
            const adminNum = Number(adminIdFromUrl);
            if (!Number.isNaN(adminNum)) {
              payload.adminid = adminNum;
            }
          }

          console.log('[App.initApp] resolveInstance payload:', payload);

          if (payload.instanceid || payload.adminid) {
            const resolveResp = await apiClient.resolveInstance(payload);
            console.log('[App.initApp] resolveInstance response:', resolveResp);

            if (resolveResp.linkforbidden) {
              linkForbidden = true;
            } else if (resolveResp.instanceid) {
              resolvedInstance = {
                instanceid: resolveResp.instanceid,
                botusername: resolveResp.botusername ?? '',
                botname: resolveResp.botname ?? '',
                role: resolveResp.role ?? 'owner',
                openchatusername: resolveResp.openchatusername ?? null,
                generalpanelchatid: resolveResp.generalpanelchatid ?? null,
              };
            } else {
              console.warn('[App.initApp] resolveInstance returned no instance_id', resolveResp);
            }
          } else {
            console.log('[App.initApp] no instance_id/admin_id in payload, skip resolveInstance');
          }
        } catch (e: any) {
          console.warn('App.initApp resolveinstance error:', e?.message || e);
        }

        if (linkForbidden) {
          setSelectedInstance(null);
          setError(t('app.ownerOnly'));
          setLoading(false);
          return;
        }

        console.log('[App.initApp] fallback instance selection', {
          instancesCount: authResponse.user.instances?.length,
        });

        const userInstancesRaw = authResponse.user.instances;
        const normalizedList: Instance[] = userInstancesRaw.map((src: any) => ({
          instanceid: src.instanceid || src.instanceid,
          botusername: src.botusername || src.botusername,
          botname: src.botname || src.botname,
          role: src.role || 'owner',
          openchatusername: src.openchatusername || src.openchatusername || null,
          generalpanelchatid: src.generalpanelchatid || src.generalpanelchatid || null,
        }));

        setInstances(normalizedList);

        if (normalizedList.length === 0) {
          console.log(
            '[App.initApp] first launch: no instances for this user, show FirstLaunch screen'
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

            const defId = authResponse.defaultinstanceid;
            if (defId) {
              const fromList = normalizedList.find((i) => i.instanceid === defId);
              if (fromList) return fromList;
            }

            return normalizedList[0] ?? null;
          });
        }

        // Always land on InstancesList after init
        setCurrentPage('instances');
        setLoading(false);

        console.log('[App.initApp] done', { resolvedInstance });
      } catch (err: any) {
        console.error('[App.initApp] FATAL', {
          message: err?.message,
          stack: err?.stack,
        });

        if (typeof err?.message === 'string' && err.message.includes('link_forbidden')) {
          setError(t('app.ownerOnly'));
        } else {
          setError(t('app.openFromTelegram'));
        }

        setLoading(false);
      }
    };

    void initApp();
  }, []);

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
    // Не загружаем данные инстанса, если идет удаление
    if (isDeleting) {
      console.log('[App] Пропускаем загрузку данных инстанса, т.к. идет удаление');
      return;
    }

    if (!selectedInstance || selectedInstance.instanceid === 'temp-loading') {
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
  }, [selectedInstance?.instanceid, isDeleting]);



  // Добавленный useEffect для динамической установки темы
  useEffect(() => {
    if (window.Telegram && window.Telegram.WebApp) {
      const webApp = window.Telegram.WebApp;

      // Установка начальной темы
      const colorScheme = webApp.colorScheme; // 'light' или 'dark'
      document.documentElement.setAttribute('data-color-scheme', colorScheme);

      // Слушатель изменений темы
      webApp.onEvent('themeChanged', () => {
        const newScheme = webApp.colorScheme;
        document.documentElement.setAttribute('data-color-scheme', newScheme);
      });

      // Инициализация WebApp
      webApp.ready();
    } else {
      // Fallback для браузера (не в Telegram)
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      document.documentElement.setAttribute('data-color-scheme', mediaQuery.matches ? 'dark' : 'light');

      mediaQuery.addEventListener('change', (e) => {
        document.documentElement.setAttribute('data-color-scheme', e.matches ? 'dark' : 'light');
      });
    }
  }, []);


  const handleCreateInstanceByToken = async (token: string) => {
    try {
      //  НЕ используем глобальный loading - вместо этого используем isCreatingInstance
      setError(null);
      setLimitMessage(null);
      setIsCreatingInstance(true);


      console.log('[App] createInstanceByToken, preview:', token.slice(0, 10));


      //  Создаём временный инстанс для немедленного показа Dashboard со скелетоном
      const tempInstance: Instance = {
        instanceid: 'temp-loading',
        botusername: '',
        botname: 'Загрузка...',
        role: 'owner',
        openchatusername: null,
        generalpanelchatid: null,
      };


      //  Сразу переключаемся на Dashboard - там будет показан скелетон
      setSelectedInstance(tempInstance);
      setIsFirstLaunch(false);
      setCurrentPage('dashboard');
      setShowAddModal(false);


      // Теперь отправляем запрос к API
      const created = await apiClient.createInstanceByToken({ 
        token,
        language: i18n.language 
      });


      console.log('[App] created instance', created);


      const normalized: Instance = {
        instanceid: created.instanceid,
        botusername: created.botusername,
        botname: created.botname,
        role: created.role || 'owner',
        openchatusername: (created as any).openchatusername ?? null,
        generalpanelchatid: (created as any).generalpanelchatid ?? null,
      };


      //  Обновляем список и выбранный инстанс реальными данными
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
            //  При ошибке лимита возвращаемся на instances
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
      //  При любой другой ошибке тоже возвращаемся
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
      
      //  Устанавливаем флаг удаления
      setIsDeleting(true);
      
      //  Сохраняем предыдущее состояние для возможного отката
      const previousInstances = [...instances];
      const previousSelectedInstance = selectedInstance;
      const previousSelectedInstanceId = selectedInstance?.instanceid;
      const wasFirstLaunch = isFirstLaunch;
      const wasOnDashboard = currentPage === 'dashboard';
      
      //  Оптимистичное обновление - сразу обновляем UI
      setInstances((prev) => {
        const filtered = prev.filter((i) => i.instanceid !== inst.instanceid);
        
        // Если удаляем выбранный инстанс
        if (previousSelectedInstanceId === inst.instanceid) {
          if (filtered.length > 0) {
            // Выбираем следующий доступный инстанс, но НЕ запускаем загрузку его данных
            const nextInstance = filtered[0];
            setSelectedInstance(nextInstance);
            
            // Если были на Dashboard, остаемся там, но с новым инстансом
            if (wasOnDashboard) {
              setCurrentPage('dashboard');
            } else {
              setCurrentPage('instances');
            }
          } else {
            // Больше нет инстансов
            setSelectedInstance(null);
            setIsFirstLaunch(true);
            setCurrentPage('instances');
          }
        }
        
        return filtered;
      });
      
      //  Удаление в фоне
      const deletePromise = apiClient.deleteInstance(inst.instanceid);
      
      // Обрабатываем успешное удаление
      deletePromise.then(() => {
        console.log('[App] Фоновое удаление успешно завершено');
      }).catch((err: any) => {
        console.error('[App] Фоновое удаление не удалось', err);
        
        //  Возвращаем инстанс обратно
        setInstances(previousInstances);
        
        // Если удаляли выбранный инстанс, возвращаем его
        if (previousSelectedInstanceId === inst.instanceid) {
          setSelectedInstance(previousSelectedInstance);
          setIsFirstLaunch(wasFirstLaunch);
          
          // Если были на Dashboard, возвращаемся с тем же инстансом
          if (wasOnDashboard && previousSelectedInstance) {
            setCurrentPage('dashboard');
          }
        }
        
        // Показываем уведомление об ошибке
        const fallback = t('firstLaunch.create_error_fallback');
        const message =
          typeof err?.message === 'string' && err.message.trim().length > 0
            ? err.message
            : fallback;
        
        // Используем небольшой таймаут, чтобы пользователь видел откат
        setTimeout(() => {
          setBackgroundError(message);
        }, 300);
      }).finally(() => {
        //  Сбрасываем флаг удаления после завершения операции
        setIsDeleting(false);
      });
      
    } catch (err: any) {
      console.error('[App] Ошибка при обработке удаления', err);
      const fallback = t('firstLaunch.create_error_fallback');
      const message =
        typeof err?.message === 'string' && err.message.trim().length > 0
          ? err.message
          : fallback;
      setError(message);
      setIsDeleting(false);
    }
  };


  const handleOpenBot = () => {
    if (!selectedInstance?.botusername) return;
    const botUrl = `https://t.me/${selectedInstance.botusername}?start=help`;
    window.open(botUrl, '_blank');
  };


  const footerBranding = (
    <div className="app-footer">
      {t('app.footerBrand')}{' '}
      <a
        href="https://github.com/glebgv/GraceHub/"
        target="_blank"
        rel="noreferrer"
        className="footer-link"
      >
        GraceHub 0.1.0a
      </a>
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
          onGoToBilling={() => {
            setIsFirstLaunch(false);
            setCurrentPage('billing');
          }}
          loading={loading && !deletingInstanceId} 
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


  // Исключаем загрузку данных из isHeaderLoading во время удаления
  const isHeaderLoading = (isCreatingInstance || instanceDataLoading) && !isDeleting;


  return (
    <div className="app-container">
      {/* Уведомление о фоновой ошибке удаления */}
      {backgroundError && (
        <div className="notification-error">
          <div className="notification-content">
            <span>⚠️ Ошибка при удалении: {backgroundError}</span>
            <button 
              className="notification-close"
              onClick={() => setBackgroundError(null)}
              aria-label="Закрыть"
            >
              ✕
            </button>
          </div>
        </div>
      )}

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


      {/* App Header - полностью скрываем на FirstLaunch (currentPage === 'instances' && instances.length === 0) */}
      {selectedInstance && !(currentPage === 'instances' && instances.length === 0) && (
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
              {isHeaderLoading ? (
                <div className="btn-back" style={{ cursor: 'default' }}>
                  <div 
                    className="skeleton animate-pulse"
                    style={{
                      display: 'block',
                      backgroundColor: '#e5e7eb',
                      minHeight: '2.5rem',
                      width: '2.5rem',
                      borderRadius: '50%'
                    }}
                  ></div>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn-back"
                  onClick={() => setCurrentPage('instances')}
                  aria-label={t('common.back', 'Назад')}
                  title={t('common.back', 'Назад')}
                >
                  ←
                </button>
              )}
            </div>
          )}
        </header>
      )}


      <main className={`main-content ${pageAnim ? 'gh-page-animating' : ''}`}>
        {currentPage === 'instances' && (
          instances.length === 0 ? (
            <FirstLaunch
              onAddBotClick={() => {
                setLimitMessage(null);
                setShowAddModal(true);
              }}
              onGoToBilling={() => {
                setSelectedInstance(null);
                setCurrentPage('billing');
              }}
              isSuperadmin={isSuperadmin}
              onOpenAdmin={isSuperadmin ? () => setCurrentPage('superadmin') : undefined}
              loading={loading && !deletingInstanceId} 
            />
          ) : (
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
              onGoToBilling={() => {
                if (instances.length > 0) {
                  setSelectedInstance(instances[0]);
                  setCurrentPage('billing');
                }
              }}
              loading={loading || !!deletingInstanceId} 
            />
          )
        )}


        {/*  Показываем Dashboard если есть selectedInstance ИЛИ идёт создание инстанса */}
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


        {currentPage === 'billing' && (
          <Billing
            instanceId={selectedInstance?.instanceid ?? null}
            onBack={() => setCurrentPage('instances')}
          />
        )}


        {currentPage === 'superadmin' && isSuperadmin && (
          <SuperAdmin
            onBack={() => {
              setCurrentPage('instances');
              setIsFirstLaunch(true);
            }}
          />
        )}
      </main>


      {footerBranding}


      {showBottomNav && (
        <nav className="app-nav">
          <div className="app-nav-inner">
            {isHeaderLoading ? (
              <>
                {/* Скелетон для кнопки Dashboard */}
                <div className="nav-button" style={{ cursor: 'default' }}>
                  <span 
                    className="skeleton animate-pulse"
                    style={{
                      display: 'block',
                      backgroundColor: '#e5e7eb',
                      minHeight: '1.5rem',
                      width: '1.5rem',
                      borderRadius: '4px',
                      margin: '0 auto 0.25rem'
                    }}
                  ></span>
                  <span 
                    className="skeleton animate-pulse"
                    style={{
                      display: 'block',
                      backgroundColor: '#e5e7eb',
                      minHeight: '0.875rem',
                      width: '4rem',
                      borderRadius: '4px',
                      margin: '0 auto'
                    }}
                  ></span>
                </div>


                {/* Скелетон для кнопки Tickets */}
                <div className="nav-button" style={{ cursor: 'default' }}>
                  <span 
                    className="skeleton animate-pulse"
                    style={{
                      display: 'block',
                      backgroundColor: '#e5e7eb',
                      minHeight: '1.5rem',
                      width: '1.5rem',
                      borderRadius: '4px',
                      margin: '0 auto 0.25rem'
                    }}
                  ></span>
                  <span 
                    className="skeleton animate-pulse"
                    style={{
                      display: 'block',
                      backgroundColor: '#e5e7eb',
                      minHeight: '0.875rem',
                      width: '3.5rem',
                      borderRadius: '4px',
                      margin: '0 auto'
                    }}
                  ></span>
                </div>


                {/* Скелетон для кнопки Operators (если role === 'owner') */}
                {selectedInstance?.role === 'owner' && (
                  <>
                    <div className="nav-button" style={{ cursor: 'default' }}>
                      <span 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '1.5rem',
                          width: '1.5rem',
                          borderRadius: '4px',
                          margin: '0 auto 0.25rem'
                        }}
                      ></span>
                      <span 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '0.875rem',
                          width: '4.5rem',
                          borderRadius: '4px',
                          margin: '0 auto'
                        }}
                      ></span>
                    </div>


                    {/* Скелетон для кнопки Settings */}
                    <div className="nav-button" style={{ cursor: 'default' }}>
                      <span 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '1.5rem',
                          width: '1.5rem',
                          borderRadius: '4px',
                          margin: '0 auto 0.25rem'
                        }}
                      ></span>
                      <span 
                        className="skeleton animate-pulse"
                        style={{
                          display: 'block',
                          backgroundColor: '#e5e7eb',
                          minHeight: '0.875rem',
                          width: '4rem',
                          borderRadius: '4px',
                          margin: '0 auto'
                        }}
                      ></span>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
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