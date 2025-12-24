import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactDOM from 'react-dom';
import { apiClient, type PaymentMethod } from '../api/client';
import { useTranslation } from 'react-i18next';

type SaasPlanDTO = {
  planCode: string;
  planName: string;
  periodDays: number;
  ticketsLimit: number;
  priceStars: number;
  productCode: string | null;
};

interface BillingProps {
  instanceId: string;
}

type PeriodOption = {
  id: string;
  multiplier: number;
  labelKey: string;
};

const periodOptions: PeriodOption[] = [
  { id: '1', multiplier: 1, labelKey: 'billing.period_1x' },
  { id: '3', multiplier: 3, labelKey: 'billing.period_3x' },
  { id: '12', multiplier: 12, labelKey: 'billing.period_12x' },
];

const TON_PENDING_KEY = 'billing:pending_ton_invoice:v1';

type PendingTonInvoice = {
  instanceId: string;
  invoiceId: number;
  invoiceLink: string;
  comment: string;
  amountTon: string;
  address: string;
  createdAt: string; // ISO
};

const savePendingTonInvoice = (data: PendingTonInvoice) => {
  try {
    localStorage.setItem(TON_PENDING_KEY, JSON.stringify(data));
  } catch {}
};

const loadPendingTonInvoice = (): PendingTonInvoice | null => {
  try {
    const raw = localStorage.getItem(TON_PENDING_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PendingTonInvoice;
  } catch {
    return null;
  }
};

const clearPendingTonInvoice = () => {
  try {
    localStorage.removeItem(TON_PENDING_KEY);
  } catch {}
};

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      return true;
    } catch {
      return false;
    }
  }
};

const CopyIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M9 9h10v12H9V9zm-4 6H4V3h12v1"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

type StripeInvoice = {
  invoiceId: number;
  invoiceLink: string;
  sessionId: string; // Из response
};

const Billing: React.FC<BillingProps> = ({ instanceId }) => {
  const { t } = useTranslation();

  const [plans, setPlans] = useState<SaasPlanDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Global payments availability (from SuperAdmin / platformsettings: miniapppublic)
  const [paymentsEnabled, setPaymentsEnabled] = useState<{
    telegramStars: boolean;
    ton: boolean;
    yookassa: boolean;
    stripe: boolean; // Новый
  }>({ telegramStars: true, ton: true, yookassa: true, stripe: true });
  const [paymentsLoading, setPaymentsLoading] = useState(true);

  const [selectedPlan, setSelectedPlan] = useState<SaasPlanDTO | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption | null>(periodOptions[0]);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // По умолчанию пусто => показываем placeholder
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [paymentResult, setPaymentResult] = useState<{ planName: string; months: number } | null>(null);

  // TON реквизиты текущего инвойса (после createBillingInvoice)
  const [tonInvoice, setTonInvoice] = useState<{
    invoiceId: number;
    invoiceLink: string;
    comment: string; // saas:<id>
    amountTon: string; // человеко-читаемая, например '0.50'
    address: string; // из invoice_link (вытаскиваем адрес из deeplink)
  } | null>(null);

  const [isTonModalOpen, setIsTonModalOpen] = useState(false);

  // TON: ручной режим проверки
  const [tonChecking, setTonChecking] = useState(false);
  const [tonCheckError, setTonCheckError] = useState<string | null>(null);
  const tonPollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  // YooKassa invoice
  const [ykInvoice, setYkInvoice] = useState<{
    invoiceId: number;
    invoiceLink: string;
  } | null>(null);

  const [isYkModalOpen, setIsYkModalOpen] = useState(false);
  const [ykChecking, setYkChecking] = useState(false);
  const [ykCheckError, setYkCheckError] = useState<string | null>(null);
  const ykPollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  // Stripe invoice
  const [stripeInvoice, setStripeInvoice] = useState<StripeInvoice | null>(null);

  const [isStripeModalOpen, setIsStripeModalOpen] = useState(false);
  const [stripeChecking, setStripeChecking] = useState(false);
  const [stripeCheckError, setStripeCheckError] = useState<string | null>(null);
  const stripePollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  // UI feedback "Скопировано"
  const [copiedMsg, setCopiedMsg] = useState<string | null>(null);
  const copiedTimerRef = useRef<number | null>(null);

  const showCopied = (msg: string) => {
    setCopiedMsg(msg);
    if (copiedTimerRef.current) window.clearTimeout(copiedTimerRef.current);
    copiedTimerRef.current = window.setTimeout(() => setCopiedMsg(null), 1500);
  };

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) window.clearTimeout(copiedTimerRef.current);
    };
  }, []);

  const iconBtnStyle: React.CSSProperties = {
    width: 32,
    height: 32,
    borderRadius: 8,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'transparent',
    cursor: 'pointer',
  };

  // Load global payment availability (SuperAdmin -> platformsettings: miniapppublic)
  useEffect(() => {
    let cancelled = false;

    const loadPaymentsEnabled = async () => {
      try {
        setPaymentsLoading(true);
        const s = await apiClient.getMiniappPublicSettings();

        if (cancelled) return;

        setPaymentsEnabled({
          telegramStars: !!s?.payments?.enabled?.telegramStars,
          ton: !!s?.payments?.enabled?.ton,
          yookassa: !!s?.payments?.enabled?.yookassa,
          stripe: !!s?.payments?.enabled?.stripe, // Новый
        });
      } catch (e: any) {
        // Fail-open to avoid breaking billing if settings are temporarily unavailable
        // (server-side still should validate method availability)
        console.warn('Failed to load miniapp public settings for payments:', e?.message || e);
        if (cancelled) return;

        setPaymentsEnabled({ telegramStars: true, ton: true, yookassa: true, stripe: true });
      } finally {
        if (!cancelled) setPaymentsLoading(false);
      }
    };

    loadPaymentsEnabled();

    return () => {
      cancelled = true;
    };
  }, []);

  const paymentMethods: Array<{ value: PaymentMethod; label: string }> = useMemo(() => {
    const out: Array<{ value: PaymentMethod; label: string }> = [];

    if (paymentsEnabled.telegramStars) out.push({ value: 'telegram_stars', label: t('billing.payment_method_stars') });
    if (paymentsEnabled.ton) out.push({ value: 'ton', label: t('billing.payment_method_ton') });
    if (paymentsEnabled.yookassa) out.push({ value: 'yookassa', label: t('billing.payment_method_yookassa') });
    if (paymentsEnabled.stripe) out.push({ value: 'stripe', label: t('billing.payment_method_stripe') });

    return out;
  }, [paymentsEnabled.telegramStars, paymentsEnabled.ton, paymentsEnabled.yookassa, paymentsEnabled.stripe, t]);

  const hasAnyPaymentMethods = paymentMethods.length > 0;

  // NEW: если вообще нет методов оплаты — в Billing не показываем тарифы
  const paymentsDisabledByAdmin = !hasAnyPaymentMethods;

  // Load plans, but ONLY if payments are enabled
  useEffect(() => {
    if (paymentsLoading) return;

    // если админ выключил ВСЕ методы — не грузим тарифы вообще
    if (paymentsDisabledByAdmin) {
      setPlans([]);
      setLoading(false);
      setError(null);
      return;
    }

    const loadPlans = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await apiClient.getSaasPlans();
        setPlans(data);
      } catch (err: any) {
        console.error('Ошибка загрузки тарифов:', err);
        setError(err.message || 'Failed to load plans');
      } finally {
        setLoading(false);
      }
    };

    loadPlans();
  }, [paymentsLoading, paymentsDisabledByAdmin]);

  // If selected method becomes unavailable (settings updated), reset to placeholder
  useEffect(() => {
    if (!paymentMethod) return;
    const stillAllowed = paymentMethods.some((m) => m.value === paymentMethod);
    if (!stillAllowed) setPaymentMethod('');
  }, [paymentMethod, paymentMethods]);

  // Restore pending TON invoice after app restart
  useEffect(() => {
    const restorePending = async () => {
      const saved = loadPendingTonInvoice();
      if (!saved) return;
      if (saved.instanceId !== instanceId) return;

      try {
        const st = await apiClient.getTonInvoiceStatus(saved.invoiceId);
        if (st.status === 'paid' && st.period_applied) {
          clearPendingTonInvoice();
          return;
        }
      } catch {
        // if status check fails, still restore UI (manual check button will work)
      }

      setTonInvoice({
        invoiceId: saved.invoiceId,
        invoiceLink: saved.invoiceLink,
        comment: saved.comment,
        amountTon: saved.amountTon,
        address: saved.address,
      });
      setIsTonModalOpen(true);
    };

    restorePending();
  }, [instanceId]);

  // Disable background scroll when ANY modal is open
  useEffect(() => {
    const anyModalOpen = isModalOpen || isTonModalOpen || isYkModalOpen || isStripeModalOpen || !!paymentResult;
    if (!anyModalOpen) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [isModalOpen, isTonModalOpen, isYkModalOpen, isStripeModalOpen, paymentResult]);

  const openPlanModal = (plan: SaasPlanDTO) => {
    setSelectedPlan(plan);
    setSelectedPeriod(periodOptions[0]);
    setPaymentMethod(''); // важно: сброс к placeholder
    setSubmitError(null);

    // reset TON state (UI only, pending invoice can still be restored on reload)
    setTonInvoice(null);
    setIsTonModalOpen(false);
    setTonChecking(false);
    setTonCheckError(null);
    tonPollAbortRef.current.aborted = true;

    // reset YooKassa state
    setYkInvoice(null);
    setIsYkModalOpen(false);
    setYkChecking(false);
    setYkCheckError(null);
    ykPollAbortRef.current.aborted = true;

    // reset Stripe state
    setStripeInvoice(null);
    setIsStripeModalOpen(false);
    setStripeChecking(false);
    setStripeCheckError(null);
    stripePollAbortRef.current.aborted = true;

    setCopiedMsg(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    // stop any polling when closing
    tonPollAbortRef.current.aborted = true;
    setTonChecking(false);

    ykPollAbortRef.current.aborted = true;
    setYkChecking(false);

    stripePollAbortRef.current.aborted = true;
    setStripeChecking(false);

    setIsModalOpen(false);
    setSelectedPlan(null);
    setSubmitError(null);

    setCopiedMsg(null);
  };

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // Открывать Tonkeeper через внешний браузер, чтобы не терялись параметры в Telegram webview
  const openTonLinkExternally = (link: string) => {
    const tg = (window as any).Telegram?.WebApp;

    try {
      tg?.openLink?.(link, { try_instant_view: false });
      return;
    } catch {}

    try {
      window.open(link, '_blank', 'noopener,noreferrer');
      return;
    } catch {}

    window.location.href = link;
  };

  const openYooKassaLinkExternally = (link: string) => {
    const tg = (window as any).Telegram?.WebApp;
    try {
      tg?.openLink?.(link, { tryinstantview: true }); 
      return;
    } catch {
      try {
        window.open(link, '_blank', 'noopener,noreferrer');
        return;
      } catch {
        window.location.href = link;
      }
    }
  };

  const openStripeLinkExternally = (link: string) => {
    const tg = (window as any).Telegram?.WebApp;
    try {
      tg?.openLink?.(link, { try_instant_view: false });
      return;
    } catch {}

    try {
      window.open(link, '_blank', 'noopener,noreferrer');
      return;
    } catch {}

    window.location.href = link;
  };

  const pollTonStatus = async (invoiceId: number, abortRef: { aborted: boolean }, timeoutMs: number = 120000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (abortRef.aborted) throw new Error('aborted');

      const st = await apiClient.getTonInvoiceStatus(invoiceId);

      if (abortRef.aborted) throw new Error('aborted');

      if (st.status === 'paid' && st.period_applied) return st;
      if (st.status === 'failed') throw new Error(t('billing.payment_failed'));

      await sleep(2500);
    }
    throw new Error(t('billing.payment_failed'));
  };

  const handleCheckTonPayment = async () => {
    if (!tonInvoice?.invoiceId) return;

    // новый цикл проверки — сбрасываем флаг abort
    tonPollAbortRef.current = { aborted: false };
    setTonChecking(true);
    setTonCheckError(null);

    try {
      const st = await pollTonStatus(tonInvoice.invoiceId, tonPollAbortRef.current, 120000);
      if (st.status === 'paid') {
        clearPendingTonInvoice();
        setIsTonModalOpen(false);
        closeModal();
        if (selectedPlan && selectedPeriod) {
          setPaymentResult({ planName: selectedPlan.planName, months: selectedPeriod.multiplier });
        }
      }
    } catch (e: any) {
      if (e?.message === 'aborted') return;
      setTonCheckError(e?.message || t('billing.payment_failed'));
    } finally {
      setTonChecking(false);
    }
  };

  const handleCancelTonPayment = () => {
    clearPendingTonInvoice();
    tonPollAbortRef.current.aborted = true;
    setTonChecking(false);
    setTonCheckError(null);

    setIsTonModalOpen(false);
    setTonInvoice(null);

    showCopied(t('billing.cancelled'));
  };

  const pollYooKassaStatus = async (invoiceId: number, abortRef: { aborted: boolean }, timeoutMs: number = 120000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (abortRef.aborted) throw new Error('aborted');

      const st = await apiClient.getYooKassaInvoiceStatus(invoiceId);

      if (abortRef.aborted) throw new Error('aborted');

      if (st.status === 'succeeded' && st.period_applied) return st;
      if (st.status === 'canceled') throw new Error(t('billing.payment_failed'));

      await sleep(2500);
    }
    throw new Error(t('billing.payment_failed'));
  };

  const handleCheckYooKassaPayment = async () => {
    if (!ykInvoice?.invoiceId) return;

    ykPollAbortRef.current = { aborted: false };
    setYkChecking(true);
    setYkCheckError(null);

    try {
      const st = await pollYooKassaStatus(ykInvoice.invoiceId, ykPollAbortRef.current, 120000);
      if (st.status === 'succeeded') {
        setIsYkModalOpen(false);
        closeModal();
        if (selectedPlan && selectedPeriod) {
          setPaymentResult({ planName: selectedPlan.planName, months: selectedPeriod.multiplier });
        }
      }
    } catch (e: any) {
      if (e?.message === 'aborted') return;
      setYkCheckError(e?.message || t('billing.payment_failed'));
    } finally {
      setYkChecking(false);
    }
  };

  const handleCancelYooKassaPayment = () => {
    ykPollAbortRef.current.aborted = true;
    setYkChecking(false);
    setYkCheckError(null);

    setIsYkModalOpen(false);
    setYkInvoice(null);

    showCopied(t('billing.cancelled'));
  };

  const pollStripeStatus = async (invoiceId: number, abortRef: { aborted: boolean }, timeoutMs: number = 120000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (abortRef.aborted) throw new Error('aborted');

      const st = await apiClient.getStripeInvoiceStatus(invoiceId);

      if (abortRef.aborted) throw new Error('aborted');

      if (st.status === 'succeeded' && st.period_applied) return st;
      if (st.status === 'failed') throw new Error(t('billing.payment_failed'));

      await sleep(2500);
    }
    throw new Error(t('billing.payment_failed'));
  };

  const handleCheckStripePayment = async () => {
    if (!stripeInvoice?.invoiceId) return;

    stripePollAbortRef.current = { aborted: false };
    setStripeChecking(true);
    setStripeCheckError(null);

    try {
      const st = await pollStripeStatus(stripeInvoice.invoiceId, stripePollAbortRef.current, 120000);
      if (st.status === 'succeeded') {
        setIsStripeModalOpen(false);
        closeModal();
        if (selectedPlan && selectedPeriod) {
          setPaymentResult({ planName: selectedPlan.planName, months: selectedPeriod.multiplier });
        }
      }
    } catch (e: any) {
      if (e?.message === 'aborted') return;
      setStripeCheckError(e?.message || t('billing.payment_failed'));
    } finally {
      setStripeChecking(false);
    }
  };

  const handleCancelStripePayment = () => {
    stripePollAbortRef.current.aborted = true;
    setStripeChecking(false);
    setStripeCheckError(null);

    setIsStripeModalOpen(false);
    setStripeInvoice(null);

    showCopied(t('billing.cancelled'));
  };

  const formatTonAmountFromResp = (resp: any): string => {
    const amtTon = resp?.amount_ton;
    if (typeof amtTon === 'number' && Number.isFinite(amtTon)) return amtTon.toFixed(2);

    const minor = resp?.amount_minor_units;
    if (typeof minor === 'number' && Number.isFinite(minor)) return (minor / 1e9).toFixed(2);

    return '0.00';
  };

  const parseTonAddressFromInvoiceLink = (invoiceLink: string): string => {
    try {
      const u = new URL(invoiceLink);
      const parts = u.pathname.split('/');
      return parts[parts.length - 1] || '';
    } catch {
      return '';
    }
  };

  const handleCreateInvoice = async () => {
    if (!selectedPlan || !selectedPeriod) return;
    if (!selectedPlan.productCode) return;

    if (!hasAnyPaymentMethods) {
      setSubmitError(t('billing.payment_failed'));
      return;
    }

    // важно: не даём отправить запрос с payment_method=''
    if (!paymentMethod) {
      setSubmitError(t('billing.choose_payment_method'));
      return;
    }

    // Extra client-side guard (server must validate too)
    const stillAllowed = paymentMethods.some((m) => m.value === paymentMethod);
    if (!stillAllowed) {
      setPaymentMethod('');
      setSubmitError(t('billing.choose_payment_method'));
      return;
    }

    try {
      setSubmitting(true);
      setSubmitError(null);

      const resp = await apiClient.createBillingInvoice(instanceId, {
        plan_code: selectedPlan.planCode,
        periods: selectedPeriod.multiplier,
        payment_method: paymentMethod,
      });

      // Stars
      if (paymentMethod === 'telegram_stars') {
        const tg = (window as any).Telegram?.WebApp;

        if (tg?.openInvoice) {
          tg.openInvoice(resp.invoice_link, (status: string) => {
            if (status === 'paid') {
              closeModal();
              setPaymentResult({ planName: selectedPlan.planName, months: selectedPeriod.multiplier });
            } else if (status === 'failed') {
              setSubmitError(t('billing.payment_failed'));
            }
          });
        } else {
          window.open(resp.invoice_link, '_blank', 'noopener,noreferrer');
        }
        return;
      }

      // TON
      if (paymentMethod === 'ton') {
        setTonCheckError(null);
        setTonChecking(false);
        tonPollAbortRef.current.aborted = true;

        const invoiceLink = resp.invoice_link as string;
        const comment = `saas:${resp.invoice_id}`;
        const amountTon = formatTonAmountFromResp(resp);
        const address = parseTonAddressFromInvoiceLink(invoiceLink);

        const nextInvoice = {
          invoiceId: resp.invoice_id,
          invoiceLink,
          comment,
          amountTon,
          address,
        };

        setTonInvoice(nextInvoice);

        savePendingTonInvoice({
          instanceId,
          invoiceId: nextInvoice.invoiceId,
          invoiceLink: nextInvoice.invoiceLink,
          comment: nextInvoice.comment,
          amountTon: nextInvoice.amountTon,
          address: nextInvoice.address,
          createdAt: new Date().toISOString(),
        });

        // важно: НЕ редиректим/не открываем кошелёк автоматически
        // открытие кошелька только по кнопке "Открыть кошелёк" в TonPaymentModal
        setIsTonModalOpen(true);
        return;
      }

      // YooKassa
      if (paymentMethod === 'yookassa') {
        setYkCheckError(null);
        setYkChecking(false);
        ykPollAbortRef.current.aborted = true;

        const invoiceLink = resp.invoice_link as string;

        setYkInvoice({
          invoiceId: resp.invoice_id,
          invoiceLink,
        });

        // тут можно открывать автоматически (в отличие от TON)
        openYooKassaLinkExternally(invoiceLink);

        setIsYkModalOpen(true);
        return;
      }

      // Stripe
      if (paymentMethod === 'stripe') {
        setStripeCheckError(null);
        setStripeChecking(false);
        stripePollAbortRef.current.aborted = true;

        setStripeInvoice({
          invoiceId: resp.invoice_id,
          invoiceLink: resp.invoice_link,
          sessionId: resp.session_id,
        });

        // открываем автоматически
        openStripeLinkExternally(resp.invoice_link);

        setIsStripeModalOpen(true);
        setIsModalOpen(false);
        return;
      }

      setSubmitError(t('billing.payment_failed'));
    } catch (e: any) {
      console.error('createBillingInvoice error', e);
      setSubmitError(e?.message || 'Failed to create invoice');
    } finally {
      setSubmitting(false);
    }
  };

  const TonPaymentModal = () => {
    if (!isTonModalOpen || !tonInvoice) return null;

    const content = (
      <div
        className="modal-backdrop"
        onClick={() => {
          setIsTonModalOpen(false);
        }}
        style={{ zIndex: 9999 }}
      >
        <div
          className="modal"
          onClick={(e) => e.stopPropagation()}
          style={{
            maxWidth: 520,
            width: 'calc(100% - 24px)',
            maxHeight: '80vh',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div className="modal-header">
            <h3 className="modal-title modal-title--gradient">{t('billing.ton_requisites_title')}</h3>
            <button
              type="button"
              className="modal-close"
              onClick={() => setIsTonModalOpen(false)}
              aria-label={t('billing.close')}
              title={t('billing.close')}
            >
              ✕
            </button>
          </div>

          <div
            className="modal-body"
            style={{
              overflowY: 'auto',
              WebkitOverflowScrolling: 'touch',
              overscrollBehavior: 'contain',
            }}
          >
            {copiedMsg && (
              <div
                style={{
                  marginBottom: 10,
                  fontSize: 12,
                  padding: '6px 8px',
                  borderRadius: 8,
                  background: 'rgba(34,197,94,0.12)',
                  border: '1px solid ' + 'rgba(34,197,94,0.25)',
                }}
              >
                {copiedMsg}
              </div>
            )}

            <div style={{ display: 'grid', rowGap: 12 }}>
              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_addr_label')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_address')}
                    title={t('billing.copy_address')}
                    onClick={async () => {
                      const ok = await copyToClipboard(tonInvoice.address);
                      showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                    }}
                  >
                    <CopyIcon />
                  </button>
                </div>
                <div style={{ wordBreak: 'break-all' }}>{tonInvoice.address}</div>
              </div>

              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_amount_label')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_amount')}
                    title={t('billing.copy_amount')}
                    onClick={async () => {
                      const val = `${tonInvoice.amountTon}`;
                      const ok = await copyToClipboard(val);
                      showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                    }}
                  >
                    <CopyIcon />
                  </button>
                </div>
                <div>{tonInvoice.amountTon} TON</div>
              </div>

              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_comment_label')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_comment')}
                    title={t('billing.copy_comment')}
                    onClick={async () => {
                      const ok = await copyToClipboard(tonInvoice.comment);
                      showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                    }}
                  >
                    <CopyIcon />
                  </button>
                </div>
                <div style={{ wordBreak: 'break-all' }}>{tonInvoice.comment}</div>
              </div>
            </div>

            <div
              style={{
                marginTop: 12,
                padding: '10px 12px',
                borderRadius: 10,
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.25)',
                fontSize: 12,
                lineHeight: 1.35,
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{t('billing.important')}</div>
              <div>{t('billing.ton_comment_required')}</div>
            </div>

            {tonCheckError && (
              <p style={{ marginTop: 10, fontSize: 12, color: 'var(--tg-color-error, #dc2626)' }}>{tonCheckError}</p>
            )}

            <p style={{ marginTop: 10, fontSize: 12, opacity: 0.85 }}>{t('billing.ton_manual_hint_short')}</p>
          </div>

          <div className="modal-footer" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              onClick={() => openTonLinkExternally(tonInvoice.invoiceLink)}
              disabled={submitting || tonChecking}
            >
              {t('billing.open_wallet_btn')}
            </button>

            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleCheckTonPayment}
              disabled={submitting || tonChecking}
            >
              {tonChecking ? t('billing.checking') : t('billing.check_payment')}
            </button>

            <button type="button" className="btn btn--ghost" onClick={handleCancelTonPayment} disabled={submitting}>
              {t('billing.cancel_payment')}
            </button>
          </div>
        </div>
      </div>
    );

    return ReactDOM.createPortal(content, document.body);
  };

  const YooKassaPaymentModal = () => {
    if (!isYkModalOpen || !ykInvoice) return null;

    const content = (
      <div className="modal-backdrop" onClick={() => setIsYkModalOpen(false)} style={{ zIndex: 9999 }}>
        <div
          className="modal"
          onClick={(e) => e.stopPropagation()}
          style={{
            maxWidth: 520,
            width: 'calc(100% - 24px)',
            maxHeight: '80vh',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div className="modal-header">
            <h3 className="modal-title modal-title--gradient">{t('billing.yk_title')}</h3>
            <button type="button" className="modal-close" onClick={() => setIsYkModalOpen(false)}>
              ✕
            </button>
          </div>

          <div className="modal-body">
            {copiedMsg && (
              <div
                style={{
                  marginBottom: 10,
                  fontSize: 12,
                  padding: '6px 8px',
                  borderRadius: 8,
                  background: 'rgba(34,197,94,0.12)',
                  border: '1px solid rgba(34,197,94,0.25)',
                }}
              >
                {copiedMsg}
              </div>
            )}

            <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>{t('billing.yk_hint')}</p>

            <div style={{ fontSize: 12, opacity: 0.8, wordBreak: 'break-all' }}>
              {t('billing.yk_invoice_id')}: {ykInvoice.invoiceId}
            </div>

            {ykCheckError && (
              <p style={{ marginTop: 10, fontSize: 12, color: 'var(--tg-color-error, #dc2626)' }}>{ykCheckError}</p>
            )}
          </div>

          <div className="modal-footer" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              onClick={() => openYooKassaLinkExternally(ykInvoice.invoiceLink)}
              disabled={submitting || ykChecking}
            >
              {t('billing.open_payment_page')}
            </button>

            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleCheckYooKassaPayment}
              disabled={submitting || ykChecking}
            >
              {ykChecking ? t('billing.checking') : t('billing.check_payment')}
            </button>

            <button type="button" className="btn btn--ghost" onClick={handleCancelYooKassaPayment} disabled={submitting}>
              {t('billing.cancel_payment')}
            </button>
          </div>
        </div>
      </div>
    );

    return ReactDOM.createPortal(content, document.body);
  };

  const StripePaymentModal = () => {
    if (!isStripeModalOpen || !stripeInvoice) return null;

    const content = (
      <div className="modal-backdrop" onClick={() => setIsStripeModalOpen(false)} style={{ zIndex: 9999 }}>
        <div
          className="modal"
          onClick={(e) => e.stopPropagation()}
          style={{
            maxWidth: 520,
            width: 'calc(100% - 24px)',
            maxHeight: '80vh',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div className="modal-header">
            <h3 className="modal-title modal-title--gradient">{t('billing.stripe_title')}</h3>
            <button type="button" className="modal-close" onClick={() => setIsStripeModalOpen(false)}>
              ✕
            </button>
          </div>

          <div className="modal-body">
            {copiedMsg && (
              <div
                style={{
                  marginBottom: 10,
                  fontSize: 12,
                  padding: '6px 8px',
                  borderRadius: 8,
                  background: 'rgba(34,197,94,0.12)',
                  border: '1px solid rgba(34,197,94,0.25)',
                }}
              >
                {copiedMsg}
              </div>
            )}

            <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>{t('billing.stripe_hint')}</p>

            <div style={{ fontSize: 12, opacity: 0.8, wordBreak: 'break-all' }}>
              {t('billing.stripe_invoice_id')}: {stripeInvoice.invoiceId}
            </div>

            {stripeCheckError && (
              <p style={{ marginTop: 10, fontSize: 12, color: 'var(--tg-color-error, #dc2626)' }}>{stripeCheckError}</p>
            )}
          </div>

          <div className="modal-footer" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              onClick={() => openStripeLinkExternally(stripeInvoice.invoiceLink)}
              disabled={submitting || stripeChecking}
            >
              {t('billing.open_payment_page')}
            </button>

            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleCheckStripePayment}
              disabled={submitting || stripeChecking}
            >
              {stripeChecking ? t('billing.checking') : t('billing.check_payment')}
            </button>

            <button type="button" className="btn btn--ghost" onClick={handleCancelStripePayment} disabled={submitting}>
              {t('billing.cancel_payment')}
            </button>
          </div>
        </div>
      </div>
    );

    return ReactDOM.createPortal(content, document.body);
  };

  if (loading || paymentsLoading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }}></div>
          <p>{t('billing.loading')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '12px' }}>
        <div
          className="card"
          style={{
            background: 'rgba(255, 51, 51, 0.1)',
            borderColor: 'rgba(255, 51, 51, 0.3)',
          }}
        >
          <p style={{ margin: 0 }}>
            {t('billing.error_prefix')}: {error}
          </p>
        </div>
      </div>
    );
  }

  // NEW: если оплаты нет — не показываем сетку тарифов, только жёлтую рамку
  if (paymentsDisabledByAdmin) {
    return (
      <div style={{ padding: '12px' }}>
        <div
          className="card"
          style={{
            background: 'rgba(245, 158, 11, 0.12)',
            borderColor: 'rgba(245, 158, 11, 0.25)',
          }}
        >
          <p style={{ margin: 0 }}>{t('billing.payments_disabled_by_admin')}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div style={{ padding: '12px' }}>
        {plans.map((plan) => (
          <div key={plan.planCode} className="card">
            <div className="list-item">
              <div className="list-item-info">
                <div className="list-item-title">{plan.planName}</div>
                <div className="list-item-subtitle">
                  {t('billing.period_and_limit', {
                    days: plan.periodDays,
                    limit: plan.ticketsLimit,
                  })}
                </div>
                <div style={{ marginTop: '4px', fontSize: '13px' }}>{plan.priceStars} ⭐</div>
              </div>
              <button className="btn" disabled={!plan.productCode} onClick={() => openPlanModal(plan)}>
                {t('billing.button_details')}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Модалка выбора тарифа */}
      {isModalOpen && selectedPlan && selectedPeriod && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: 420,
              maxHeight: '80vh',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div className="modal-header">
              <h3 className="modal-title modal-title--gradient">{t('billing.modal_title', { name: selectedPlan.planName })}</h3>
              <button type="button" className="modal-close" onClick={closeModal}>
                ✕
              </button>
            </div>

            <div
              className="modal-body"
              style={{
                overflowY: 'auto',
                WebkitOverflowScrolling: 'touch',
                overscrollBehavior: 'contain',
              }}
            >
              <p style={{ marginBottom: 8, fontSize: 13, opacity: 0.85 }}>
                {t('billing.modal_description', {
                  name: selectedPlan.planName,
                  ticketsLimit: selectedPlan.ticketsLimit,
                })}
              </p>

              <p style={{ marginBottom: 4, fontSize: 13, opacity: 0.8 }}>
                {t('billing.base_period', {
                  days: selectedPlan.periodDays,
                  limit: selectedPlan.ticketsLimit,
                })}
              </p>

              {/* Способ оплаты (dropdown) */}
              <div style={{ marginTop: 12 }}>
                <div className="modal-section-title">{t('billing.payment_method_label')}</div>

                {/* В этой модалке блок про "нет способов оплаты" можно оставить (на случай, если модалка уже открыта, а админ выключил оплаты). */}
                {!hasAnyPaymentMethods && (
                  <div
                    style={{
                      marginBottom: 10,
                      padding: '10px 12px',
                      borderRadius: 10,
                      background: 'rgba(245, 158, 11, 0.12)',
                      border: '1px solid rgba(245, 158, 11, 0.25)',
                      fontSize: 12,
                      lineHeight: 1.35,
                    }}
                  >
                    {t('billing.payments_disabled_by_admin')}
                  </div>
                )}

                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod | '')}
                  disabled={!hasAnyPaymentMethods || submitting || tonChecking || ykChecking || stripeChecking}
                  className="modal-select"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 10,
                    background: 'rgba(15,23,42,0.04)',
                    border: '1px solid rgba(148,163,184,0.7)',
                    color: 'var(--tg-theme-text-color, #0f172a)',
                    outline: 'none',
                  }}
                >
                  <option value="" disabled>
                    {t('billing.payment_method_placeholder')}
                  </option>

                  {paymentMethods.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>

                {paymentMethod === 'ton' && <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>{t('billing.ton_hint')}</p>}

                {paymentMethod === 'yookassa' && (
                  <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>{t('billing.yk_hint_inline')}</p>
                )}

                {paymentMethod === 'stripe' && <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>{t('billing.stripe_hint')}</p>}
              </div>

              {/* Выбор периода */}
              <div style={{ marginTop: 12 }}>
                <div className="modal-section-title">{t('billing.choose_period_label')}</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {periodOptions.map((opt) => {
                    const isActive = opt.id === selectedPeriod.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setSelectedPeriod(opt)}
                        className={`btn ${isActive ? 'btn--ghost' : 'btn--ghost'}`} // обе ghost, но active светлее
                        style={{
                          flex: '1 1 0',
                          position: 'relative',
                          // Активная: светлый фон + яркая обводка
                          backgroundColor: isActive ? 'rgba(255,255,255,0.15)' : 'transparent',
                          border: isActive ? '2px solid var(--tg-color-accent, #3b82f6)' : '1px solid rgba(148,163,184,0.3)',
                          color: isActive ? 'var(--tg-color-text)' : 'var(--tg-color-hint-color)',
                          minHeight: '44px',
                        }}
                        disabled={submitting || tonChecking || ykChecking || stripeChecking}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                          <span>{t(opt.labelKey, { months: opt.multiplier })}</span>
                          {isActive && (
                            <span
                              style={{
                                fontSize: '16px',
                                fontWeight: 'bold',
                                color: 'var(--tg-color-accent, #3b82f6)',
                              }}
                            >
                              ✓
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Итоговая цена и длительность */}
              <div style={{ marginTop: 16 }}>
                <div className="modal-section-title">{t('billing.final_period_label')}</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {t('billing.period_and_limit', {
                    days: selectedPlan.periodDays * selectedPeriod.multiplier,
                    limit: selectedPlan.ticketsLimit,
                  })}
                </div>

                <div className="modal-section-title" style={{ marginTop: 8 }}>
                  {t('billing.final_price_label')}
                </div>

                <div style={{ fontSize: 16, fontWeight: 600 }}>
                  {paymentMethod === 'telegram_stars'
                    ? `${selectedPlan.priceStars * selectedPeriod.multiplier} ⭐`
                    : paymentMethod === 'ton'
                      ? t('billing.ton_price_after_invoice')
                      : paymentMethod === 'yookassa'
                        ? t('billing.yk_price_after_invoice')
                        : paymentMethod === 'stripe'
                          ? t('billing.stripe_price_after_invoice')
                          : '—'}
                </div>

                {submitError && (
                  <p style={{ marginTop: 8, fontSize: 12, color: 'var(--tg-color-error, #dc2626)' }}>{submitError}</p>
                )}
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={closeModal}
                disabled={submitting || tonChecking || ykChecking || stripeChecking}
              >
                {t('billing.button_cancel')}
              </button>

              <button
                type="button"
                className="btn"
                disabled={!selectedPlan.productCode || !paymentMethod || !hasAnyPaymentMethods || submitting || tonChecking || ykChecking || stripeChecking}
                onClick={handleCreateInvoice}
              >
                {submitting ? t('billing.button_processing') : t('billing.button_choose')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Отдельные окна оплаты */}
      <TonPaymentModal />
      <YooKassaPaymentModal />
      <StripePaymentModal />

      {/* Модалка успеха */}
      {paymentResult && (
        <div
          className="modal-backdrop"
          onClick={() => {
            setPaymentResult(null);
            window.location.reload();
          }}
        >
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: 420,
              maxHeight: '80vh',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div className="modal-header">
              <h3 className="modal-title modal-title--gradient">{t('billing.payment_success_title')}</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => {
                  setPaymentResult(null);
                  window.location.reload();
                }}
              >
                ✕
              </button>
            </div>

            <div
              className="modal-body"
              style={{
                overflowY: 'auto',
                WebkitOverflowScrolling: 'touch',
                overscrollBehavior: 'contain',
              }}
            >
              <p style={{ marginBottom: 8 }}>
                {t('billing.payment_success_body', { name: paymentResult.planName, months: paymentResult.months })}
              </p>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setPaymentResult(null);
                  window.location.reload();
                }}
              >
                {t('billing.payment_success_ok')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default Billing;