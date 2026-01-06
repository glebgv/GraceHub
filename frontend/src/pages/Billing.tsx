// src/pages/Billing.tsx
// creator GraceHub Tg: @Gribson_Micro

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiClient, type PaymentMethod } from '../api/client';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';

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
  createdAt: string;
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
  sessionId: string;
};

const Billing: React.FC<BillingProps> = ({ instanceId }) => {
  const { t } = useTranslation();

  const [plans, setPlans] = useState<SaasPlanDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [paymentsEnabled, setPaymentsEnabled] = useState<{
    telegramStars: boolean;
    ton: boolean;
    yookassa: boolean;
    stripe: boolean;
  }>({ telegramStars: true, ton: true, yookassa: true, stripe: true });
  const [paymentsLoading, setPaymentsLoading] = useState(true);
  const [paymentPrices, setPaymentPrices] = useState<any>(null);

  const [selectedPlan, setSelectedPlan] = useState<SaasPlanDTO | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption | null>(periodOptions[0]);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [paymentResult, setPaymentResult] = useState<{ planName: string; months: number } | null>(
    null
  );

  const [tonInvoice, setTonInvoice] = useState<{
    invoiceId: number;
    invoiceLink: string;
    comment: string;
    amountTon: string;
    address: string;
  } | null>(null);

  const [isTonModalOpen, setIsTonModalOpen] = useState(false);

  const [tonChecking, setTonChecking] = useState(false);
  const [tonCheckError, setTonCheckError] = useState<string | null>(null);
  const tonPollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  const [ykInvoice, setYkInvoice] = useState<{
    invoiceId: number;
    invoiceLink: string;
  } | null>(null);

  const [isYkModalOpen, setIsYkModalOpen] = useState(false);
  const [ykChecking, setYkChecking] = useState(false);
  const [ykCheckError, setYkCheckError] = useState<string | null>(null);
  const ykPollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  const [stripeInvoice, setStripeInvoice] = useState<StripeInvoice | null>(null);

  const [isStripeModalOpen, setIsStripeModalOpen] = useState(false);
  const [stripeChecking, setStripeChecking] = useState(false);
  const [stripeCheckError, setStripeCheckError] = useState<string | null>(null);
  const stripePollAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  const [copiedMsg, setCopiedMsg] = useState<string | null>(null);
  const copiedTimerRef = useRef<number | null>(null);

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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
          stripe: !!s?.payments?.enabled?.stripe,
        });
        setPaymentPrices(s.payments);
      } catch (e: any) {
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

    if (paymentsEnabled.telegramStars)
      out.push({ value: 'telegram_stars', label: t('billing.payment_method_stars') });
    if (paymentsEnabled.ton) out.push({ value: 'ton', label: t('billing.payment_method_ton') });
    if (paymentsEnabled.yookassa)
      out.push({ value: 'yookassa', label: t('billing.payment_method_yookassa') });
    if (paymentsEnabled.stripe)
      out.push({ value: 'stripe', label: t('billing.payment_method_stripe') });

    return out;
  }, [
    paymentsEnabled.telegramStars,
    paymentsEnabled.ton,
    paymentsEnabled.yookassa,
    paymentsEnabled.stripe,
    t,
  ]);

  const hasAnyPaymentMethods = paymentMethods.length > 0;
  const paymentsDisabledByAdmin = !hasAnyPaymentMethods;

  useEffect(() => {
    if (paymentsLoading) return;

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

  useEffect(() => {
    if (!paymentMethod) return;
    const stillAllowed = paymentMethods.some((m) => m.value === paymentMethod);
    if (!stillAllowed) setPaymentMethod('');
  }, [paymentMethod, paymentMethods]);

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
      } catch {}

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

  const openPlanModal = (plan: SaasPlanDTO) => {
    setSelectedPlan(plan);
    setSelectedPeriod(periodOptions[0]);
    setPaymentMethod('');
    setSubmitError(null);

    setTonInvoice(null);
    setIsTonModalOpen(false);
    setTonChecking(false);
    setTonCheckError(null);
    tonPollAbortRef.current.aborted = true;

    setYkInvoice(null);
    setIsYkModalOpen(false);
    setYkChecking(false);
    setYkCheckError(null);
    ykPollAbortRef.current.aborted = true;

    setStripeInvoice(null);
    setIsStripeModalOpen(false);
    setStripeChecking(false);
    setStripeCheckError(null);
    stripePollAbortRef.current.aborted = true;

    setCopiedMsg(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
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
      tg?.openLink?.(link, { try_instant_view: true });
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

  const pollTonStatus = async (
    invoiceId: number,
    abortRef: { aborted: boolean },
    timeoutMs: number = 120000
  ) => {
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

  const pollYooKassaStatus = async (
    invoiceId: number,
    abortRef: { aborted: boolean },
    timeoutMs: number = 120000
  ) => {
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

  const pollStripeStatus = async (
    invoiceId: number,
    abortRef: { aborted: boolean },
    timeoutMs: number = 120000
  ) => {
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

    if (!paymentMethod) {
      setSubmitError(t('billing.choose_payment_method'));
      return;
    }

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
              setPaymentResult({
                planName: selectedPlan.planName,
                months: selectedPeriod.multiplier,
              });
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

  if (loading || paymentsLoading) {
    return (
      <div className="billing-page">
        <div className="card billing-loading">
          <div className="loading-spinner" />
          <p>{t('billing.loading')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="billing-page">
        <div className="card error-card">
          <p className="error-text">
            {t('billing.error_prefix')}: {error}
          </p>
        </div>
      </div>
    );
  }

  if (paymentsDisabledByAdmin) {
    return (
      <div className="billing-page">
        <div className="card warning-card">
          <p className="warning-text">{t('billing.payments_disabled_by_admin')}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="billing-page">
        {plans
          .filter((plan) => plan.planName !== 'Demo')
          .map((plan) => (
            <div key={plan.planCode} className="card billing-plan-card">
              <div className="billing-plan-content">
                <div className="billing-plan-info">
                  <div className="billing-plan-title">{plan.planName}</div>
                  <div className="billing-plan-subtitle">
                    {t('billing.period_and_limit', {
                      days: plan.periodDays,
                      limit: plan.ticketsLimit,
                    })}
                  </div>
                  <div className="billing-plan-price">
                    {(() => {
                      const enabled = paymentMethods.map((m) => m.value);
                      const hasStars = enabled.includes('telegram_stars');
                      const hasOther = enabled.some((v) => v !== 'telegram_stars');

                      if (hasStars && !hasOther) {
                        return <>{plan.priceStars} ⭐</>;
                      }

                      if (hasStars && hasOther) {
                        return (
                          <>
                            от {plan.priceStars} ⭐ ·{' '}
                            {t('billing.and_other_methods', 'и другие способы')}
                          </>
                        );
                      }

                      return <>{t('billing.price_after_invoice_short', 'Цена после выбора метода')}</>;
                    })()}
                  </div>

                  <div className="billing-plan-methods">
                    {paymentMethods.map((m) => (
                      <span key={m.value} className="billing-method-badge">
                        {m.value === 'telegram_stars' ? '⭐ ' : ''}
                        {m.label}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  className="btn btn--primary"
                  disabled={!plan.productCode}
                  onClick={() => openPlanModal(plan)}
                >
                  {t('billing.button_details')}
                </button>
              </div>
            </div>
          ))}
      </div>

      {/* Plan Selection Modal (Vaul) */}
      <Drawer.Root
        open={isModalOpen && !!selectedPlan && !!selectedPeriod}
        onOpenChange={(open) => {
          if (!open) closeModal();
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content billing-drawer">
            <div className="drawer-handle-container">
              <div className="drawer-handle" />

              <h3 className="drawer-title">
                💳 {t('billing.modal_title', { name: selectedPlan?.planName })}
              </h3>
            </div>

            <div className="drawer-body-scroll">
              <p className="billing-modal-description">
                {t('billing.modal_description', {
                  name: selectedPlan?.planName,
                  ticketsLimit: selectedPlan?.ticketsLimit,
                })}
              </p>

              <p className="billing-modal-base-period">
                {t('billing.base_period', {
                  days: selectedPlan?.periodDays,
                  limit: selectedPlan?.ticketsLimit,
                })}
              </p>

              {/* Payment Method Dropdown */}
              <div ref={dropdownRef} className="billing-dropdown-wrapper">
                <div className="billing-section-label">{t('billing.payment_method_label')}</div>

                {!hasAnyPaymentMethods && (
                  <div className="warning-banner">{t('billing.payments_disabled_by_admin')}</div>
                )}

                <div
                  className={`billing-custom-select ${
                    !hasAnyPaymentMethods || submitting || tonChecking || ykChecking || stripeChecking
                      ? 'disabled'
                      : ''
                  } ${!paymentMethod ? 'placeholder' : ''}`}
                  onClick={() =>
                    !(
                      !hasAnyPaymentMethods ||
                      submitting ||
                      tonChecking ||
                      ykChecking ||
                      stripeChecking
                    ) && setIsDropdownOpen(!isDropdownOpen)
                  }
                >
                  <span>
                    {paymentMethod
                      ? paymentMethods.find((m) => m.value === paymentMethod)?.label
                      : t('billing.payment_method_placeholder')}
                  </span>
                  <span className="billing-select-arrow">▼</span>
                </div>

                {isDropdownOpen && (
                  <ul className="billing-dropdown-menu">
                    {paymentMethods.map((m) => (
                      <li
                        key={m.value}
                        className="billing-dropdown-item"
                        onClick={() => {
                          setPaymentMethod(m.value);
                          setIsDropdownOpen(false);
                        }}
                      >
                        {m.label}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {paymentMethod === 'ton' && (
                <p className="billing-payment-hint">{t('billing.ton_hint')}</p>
              )}

              {paymentMethod === 'yookassa' && (
                <p className="billing-payment-hint">{t('billing.yk_hint_inline')}</p>
              )}

              {paymentMethod === 'stripe' && (
                <p className="billing-payment-hint">{t('billing.stripe_hint')}</p>
              )}

              {/* Period Selection */}
              <div className="billing-period-section">
                <div className="billing-section-label">{t('billing.choose_period_label')}</div>
                <div className="billing-period-buttons">
                  {periodOptions.map((opt) => {
                    const isActive = opt.id === selectedPeriod?.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setSelectedPeriod(opt)}
                        className={`btn billing-period-btn ${isActive ? 'active' : ''}`}
                        disabled={submitting || tonChecking || ykChecking || stripeChecking}
                      >
                        <span>{t(opt.labelKey, { months: opt.multiplier })}</span>
                        {isActive && <span className="billing-period-check">✓</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Final Price */}
              <div className="billing-summary">
                <div className="billing-section-label">{t('billing.final_period_label')}</div>
                <div className="billing-summary-text">
                  {t('billing.period_and_limit', {
                    days: (selectedPlan?.periodDays || 0) * (selectedPeriod?.multiplier || 1),
                    limit: selectedPlan?.ticketsLimit,
                  })}
                </div>

                <div className="billing-section-label billing-price-label">
                  {t('billing.final_price_label')}
                </div>

                <div className="billing-final-price">
                  {(() => {
                    const getDisplayPrice = () => {
                      if (!paymentMethod) return '—';

                      const planCode = selectedPlan?.planCode.toLowerCase() || '';
                      const periods = selectedPeriod?.multiplier || 1;

                      if (paymentMethod === 'telegram_stars') {
                        return `${(selectedPlan?.priceStars || 0) * periods} ⭐`;
                      }

                      if (!paymentPrices) return '—';

                      const methodPrices = paymentPrices[paymentMethod];
                      if (!methodPrices) return t('billing.price_after_invoice');

                      const priceField = `price${
                        paymentMethod === 'ton'
                          ? 'PerPeriod'
                          : paymentMethod === 'yookassa'
                            ? 'Rub'
                            : 'Usd'
                      }${planCode.charAt(0).toUpperCase() + planCode.slice(1)}`;

                      const basePrice = methodPrices[priceField] || 0;
                      const total = basePrice * periods;
                      const formatted = total.toFixed(2);

                      switch (paymentMethod) {
                        case 'ton':
                          return `${formatted} TON`;
                        case 'yookassa':
                          return `${Math.round(total)} RUB`;
                        case 'stripe': {
                          const currency = methodPrices.currency?.toUpperCase() || 'USD';
                          return `${formatted} ${currency}`;
                        }
                        default:
                          return '—';
                      }
                    };
                    return getDisplayPrice();
                  })()}
                </div>

                {submitError && <p className="billing-error-text">{submitError}</p>}
              </div>
            </div>

            <div className="drawer-footer">
              <button
                type="button"
                className="btn btn--outline"
                onClick={closeModal}
                disabled={submitting || tonChecking || ykChecking || stripeChecking}
              >
                {t('billing.button_cancel')}
              </button>

              <button
                type="button"
                className="btn btn--primary"
                disabled={
                  !selectedPlan?.productCode ||
                  !paymentMethod ||
                  !hasAnyPaymentMethods ||
                  submitting ||
                  tonChecking ||
                  ykChecking ||
                  stripeChecking
                }
                onClick={handleCreateInvoice}
              >
                {submitting ? t('billing.button_processing') : t('billing.button_choose')}
              </button>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* TON Payment Modal (Vaul) */}
      <Drawer.Root
        open={isTonModalOpen && !!tonInvoice}
        onOpenChange={(open) => {
          if (!open) setIsTonModalOpen(false);
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content billing-drawer">
            <div className="drawer-handle-container">
              <div className="drawer-handle" />

              <h3 className="drawer-title">💎 {t('billing.ton_requisites_title')}</h3>
            </div>

            <div className="drawer-body-scroll">
              {copiedMsg && <div className="success-banner">{copiedMsg}</div>}

              <div className="billing-ton-fields">
                <div className="billing-ton-field">
                  <div className="billing-ton-field-label">
                    <span>{t('billing.ton_addr_label')}</span>
                    <button
                      type="button"
                      className="billing-icon-btn"
                      aria-label={t('billing.copy_address')}
                      title={t('billing.copy_address')}
                      onClick={async () => {
                        const ok = await copyToClipboard(tonInvoice?.address || '');
                        showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                      }}
                    >
                      <CopyIcon />
                    </button>
                  </div>
                  <div className="billing-ton-field-value">{tonInvoice?.address}</div>
                </div>

                <div className="billing-ton-field">
                  <div className="billing-ton-field-label">
                    <span>{t('billing.ton_amount_label')}</span>
                    <button
                      type="button"
                      className="billing-icon-btn"
                      aria-label={t('billing.copy_amount')}
                      title={t('billing.copy_amount')}
                      onClick={async () => {
                        const val = `${tonInvoice?.amountTon}`;
                        const ok = await copyToClipboard(val);
                        showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                      }}
                    >
                      <CopyIcon />
                    </button>
                  </div>
                  <div className="billing-ton-field-value">{tonInvoice?.amountTon} TON</div>
                </div>

                <div className="billing-ton-field">
                  <div className="billing-ton-field-label">
                    <span>{t('billing.ton_comment_label')}</span>
                    <button
                      type="button"
                      className="billing-icon-btn"
                      aria-label={t('billing.copy_comment')}
                      title={t('billing.copy_comment')}
                      onClick={async () => {
                        const ok = await copyToClipboard(tonInvoice?.comment || '');
                        showCopied(ok ? t('billing.copied') : t('billing.copy_failed'));
                      }}
                    >
                      <CopyIcon />
                    </button>
                  </div>
                  <div className="billing-ton-field-value">{tonInvoice?.comment}</div>
                </div>
              </div>

              <div className="warning-banner important-banner">
                <div className="important-banner-title">{t('billing.important')}</div>
                <div>{t('billing.ton_comment_required')}</div>
              </div>

              {tonCheckError && <p className="billing-error-text">{tonCheckError}</p>}

              <p className="billing-hint-text">{t('billing.ton_manual_hint_short')}</p>
            </div>

            <div className="drawer-footer-wrap">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => openTonLinkExternally(tonInvoice?.invoiceLink || '')}
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

              <button
                type="button"
                className="btn btn--outline"
                onClick={handleCancelTonPayment}
                disabled={submitting}
              >
                {t('billing.cancel_payment')}
              </button>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* YooKassa Payment Modal (Vaul) */}
      <Drawer.Root
        open={isYkModalOpen && !!ykInvoice}
        onOpenChange={(open) => {
          if (!open) setIsYkModalOpen(false);
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content billing-drawer">
            <div className="drawer-handle-container">
              <div className="drawer-handle" />

              <h3 className="drawer-title">💳 {t('billing.yk_title')}</h3>
            </div>

            <div className="drawer-body-scroll">
              {copiedMsg && <div className="success-banner">{copiedMsg}</div>}

              <p className="billing-modal-description">{t('billing.yk_hint')}</p>

              <div className="billing-invoice-id">
                {t('billing.yk_invoice_id')}: {ykInvoice?.invoiceId}
              </div>

              {ykCheckError && <p className="billing-error-text">{ykCheckError}</p>}
            </div>

            <div className="drawer-footer-wrap">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => openYooKassaLinkExternally(ykInvoice?.invoiceLink || '')}
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

              <button
                type="button"
                className="btn btn--outline"
                onClick={handleCancelYooKassaPayment}
                disabled={submitting}
              >
                {t('billing.cancel_payment')}
              </button>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Stripe Payment Modal (Vaul) */}
      <Drawer.Root
        open={isStripeModalOpen && !!stripeInvoice}
        onOpenChange={(open) => {
          if (!open) setIsStripeModalOpen(false);
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content billing-drawer">
            <div className="drawer-handle-container">
              <div className="drawer-handle" />

              <h3 className="drawer-title">💳 {t('billing.stripe_title')}</h3>
            </div>

            <div className="drawer-body-scroll">
              {copiedMsg && <div className="success-banner">{copiedMsg}</div>}

              <p className="billing-modal-description">{t('billing.stripe_hint')}</p>

              <div className="billing-invoice-id">
                {t('billing.stripe_invoice_id')}: {stripeInvoice?.invoiceId}
              </div>

              {stripeCheckError && <p className="billing-error-text">{stripeCheckError}</p>}
            </div>

            <div className="drawer-footer-wrap">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => openStripeLinkExternally(stripeInvoice?.invoiceLink || '')}
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

              <button
                type="button"
                className="btn btn--outline"
                onClick={handleCancelStripePayment}
                disabled={submitting}
              >
                {t('billing.cancel_payment')}
              </button>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Payment Success Modal (Vaul) */}
      <Drawer.Root
        open={!!paymentResult}
        onOpenChange={(open) => {
          if (!open) {
            setPaymentResult(null);
            window.location.reload();
          }
        }}
        modal
      >
        <Drawer.Portal>
          <Drawer.Overlay className="drawer-overlay" />
          <Drawer.Content className="drawer-content billing-drawer-simple">
            <div className="drawer-body">
              <div className="drawer-handle" />

              <h3 className="drawer-title">✅ {t('billing.payment_success_title')}</h3>

              <p className="billing-success-text">
                {t('billing.payment_success_body', {
                  name: paymentResult?.planName,
                  months: paymentResult?.months,
                })}
              </p>

              <button
                type="button"
                className="btn btn--primary btn--fullwidth"
                onClick={() => {
                  setPaymentResult(null);
                  window.location.reload();
                }}
              >
                {t('billing.payment_success_ok')}
              </button>
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </>
  );
};

export default Billing;
