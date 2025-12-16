import React, { useEffect, useRef, useState } from 'react';
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

const Billing: React.FC<BillingProps> = ({ instanceId }) => {
  const { t } = useTranslation();

  const [plans, setPlans] = useState<SaasPlanDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedPlan, setSelectedPlan] = useState<SaasPlanDTO | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption | null>(periodOptions[0]);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // По умолчанию пусто => показываем placeholder "Выберите способ оплаты"
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

  useEffect(() => {
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
  }, []);

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
    const anyModalOpen = isModalOpen || isTonModalOpen || isYkModalOpen || !!paymentResult;
    if (!anyModalOpen) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [isModalOpen, isTonModalOpen, isYkModalOpen, paymentResult]);

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

    setCopiedMsg(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    // stop any polling when closing
    tonPollAbortRef.current.aborted = true;
    setTonChecking(false);

    ykPollAbortRef.current.aborted = true;
    setYkChecking(false);

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

    showCopied(t('billing.cancelled', 'Отменено'));
  };

  const pollYooKassaStatus = async (
    invoiceId: number,
    abortRef: { aborted: boolean },
    timeoutMs: number = 120000,
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

    showCopied(t('billing.cancelled', 'Отменено'));
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

    // важно: не даём отправить запрос с payment_method=''
    if (!paymentMethod) {
      setSubmitError(t('billing.choose_payment_method', 'Выберите способ оплаты'));
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

      setSubmitError(t('billing.payment_failed', 'Неизвестный способ оплаты'));
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
            <h3 className="modal-title">{t('billing.ton_requisites_title', 'Реквизиты для оплаты TON')}</h3>
            <button
              type="button"
              className="modal-close"
              onClick={() => setIsTonModalOpen(false)}
              aria-label={t('billing.close', 'Закрыть')}
              title={t('billing.close', 'Закрыть')}
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
                  border: '1px solid rgba(34,197,94,0.25)',
                }}
              >
                {copiedMsg}
              </div>
            )}

            <div style={{ display: 'grid', rowGap: 12 }}>
              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_addr_label', 'Адрес')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_address', 'Скопировать адрес')}
                    title={t('billing.copy_address', 'Скопировать адрес')}
                    onClick={async () => {
                      const ok = await copyToClipboard(tonInvoice.address);
                      showCopied(ok ? t('billing.copied', 'Скопировано') : t('billing.copy_failed', 'Не удалось скопировать'));
                    }}
                  >
                    <CopyIcon />
                  </button>
                </div>
                <div style={{ wordBreak: 'break-all' }}>{tonInvoice.address}</div>
              </div>

              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_amount_label', 'Сумма')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_amount', 'Скопировать сумму')}
                    title={t('billing.copy_amount', 'Скопировать сумму')}
                    onClick={async () => {
                      const val = `${tonInvoice.amountTon}`;
                      const ok = await copyToClipboard(val);
                      showCopied(ok ? t('billing.copied', 'Скопировано') : t('billing.copy_failed', 'Не удалось скопировать'));
                    }}
                  >
                    <CopyIcon />
                  </button>
                </div>
                <div>{tonInvoice.amountTon} TON</div>
              </div>

              <div>
                <div style={{ fontSize: 12, opacity: 0.75, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('billing.ton_comment_label', 'Комментарий')}</span>
                  <button
                    type="button"
                    style={iconBtnStyle}
                    aria-label={t('billing.copy_comment', 'Скопировать комментарий')}
                    title={t('billing.copy_comment', 'Скопировать комментарий')}
                    onClick={async () => {
                      const ok = await copyToClipboard(tonInvoice.comment);
                      showCopied(ok ? t('billing.copied', 'Скопировано') : t('billing.copy_failed', 'Не удалось скопировать'));
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
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{t('billing.important', 'Важно')}</div>
              <div>
                {t(
                  'billing.ton_comment_required',
                  'Обязательно укажите комментарий, иначе платёж не засчитается автоматически.',
                )}
              </div>
            </div>

            {tonCheckError && (
              <p style={{ marginTop: 10, fontSize: 12, color: 'var(--tg-color-error, #dc2626)' }}>{tonCheckError}</p>
            )}

            <p style={{ marginTop: 10, fontSize: 12, opacity: 0.85 }}>
              {t(
                'billing.ton_manual_hint_short',
                'Если кошелёк не установлен или данные не заполнились автоматически — установите кошелёк и отправьте перевод по реквизитам выше.',
              )}
            </p>
          </div>

          <div className="modal-footer" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              onClick={() => openTonLinkExternally(tonInvoice.invoiceLink)}
              disabled={submitting || tonChecking}
            >
              {t('billing.open_wallet_btn', 'Открыть кошелёк')}
            </button>

            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleCheckTonPayment}
              disabled={submitting || tonChecking}
            >
              {tonChecking ? t('billing.checking', 'Проверяем...') : t('billing.check_payment', 'Проверить оплату')}
            </button>

            <button type="button" className="btn btn--ghost" onClick={handleCancelTonPayment} disabled={submitting}>
              {t('billing.cancel_payment', 'Отмена оплаты')}
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
            <h3 className="modal-title">{t('billing.yk_title', 'Оплата ЮKassa')}</h3>
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

            <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
              {t('billing.yk_hint', 'Оплатите по ссылке, затем вернитесь и нажмите “Проверить оплату”.')}
            </p>

            <div style={{ fontSize: 12, opacity: 0.8, wordBreak: 'break-all' }}>
              {t('billing.yk_invoice_id', 'Invoice')}: {ykInvoice.invoiceId}
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
              {t('billing.open_payment_page', 'Открыть страницу оплаты')}
            </button>

            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleCheckYooKassaPayment}
              disabled={submitting || ykChecking}
            >
              {ykChecking ? t('billing.checking', 'Проверяем...') : t('billing.check_payment', 'Проверить оплату')}
            </button>

            <button type="button" className="btn btn--ghost" onClick={handleCancelYooKassaPayment} disabled={submitting}>
              {t('billing.cancel_payment', 'Отмена оплаты')}
            </button>
          </div>
        </div>
      </div>
    );

    return ReactDOM.createPortal(content, document.body);
  };

  const paymentMethods: Array<{ value: PaymentMethod; label: string }> = [
    { value: 'telegram_stars', label: t('billing.payment_method_stars', 'Telegram Stars') },
    { value: 'ton', label: t('billing.payment_method_ton', 'TON') },
    { value: 'yookassa', label: t('billing.payment_method_yookassa', 'ЮKassa (карта/СБП)') },
  ];

  if (loading) {
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
              <h3 className="modal-title">{t('billing.modal_title', { name: selectedPlan.planName })}</h3>
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
              <p style={{ marginBottom: 8 }}>
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
                <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 500 }}>
                  {t('billing.payment_method_label', 'Способ оплаты')}
                </div>

                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod | '')}
                  disabled={submitting || tonChecking || ykChecking}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 10,
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: 'inherit',
                    outline: 'none',
                  }}
                >
                  <option value="" disabled>
                    {t('billing.payment_method_placeholder', 'Выберите способ оплаты')}
                  </option>

                  {paymentMethods.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>

                {paymentMethod === 'ton' && (
                  <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
                    {t(
                      'billing.ton_hint',
                      'Нажмите "Выбрать", затем нажмите "Открыть кошелёк" и оплатите. После оплаты вернитесь сюда и нажмите "Проверить оплату".',
                    )}
                  </p>
                )}

                {paymentMethod === 'yookassa' && (
                  <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
                    {t(
                      'billing.yk_hint_inline',
                      'Нажмите "Выбрать", оплатите в ЮKassa, затем вернитесь и нажмите "Проверить оплату".',
                    )}
                  </p>
                )}
              </div>

              {/* Выбор периода */}
              <div style={{ marginTop: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 500 }}>{t('billing.choose_period_label')}</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {periodOptions.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setSelectedPeriod(opt)}
                      className={opt.id === selectedPeriod.id ? 'btn btn--secondary' : 'btn btn--ghost'}
                      style={{ flex: '1 1 0' }}
                      disabled={submitting || tonChecking || ykChecking}
                    >
                      {t(opt.labelKey, { months: opt.multiplier })}
                    </button>
                  ))}
                </div>
              </div>

              {/* Итоговая цена и длительность */}
              <div style={{ marginTop: 16 }}>
                <div style={{ fontSize: 13, opacity: 0.8 }}>{t('billing.final_period_label')}</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {t('billing.period_and_limit', {
                    days: selectedPlan.periodDays * selectedPeriod.multiplier,
                    limit: selectedPlan.ticketsLimit,
                  })}
                </div>

                <div style={{ marginTop: 8, fontSize: 13, opacity: 0.8 }}>{t('billing.final_price_label')}</div>

                <div style={{ fontSize: 16, fontWeight: 600 }}>
                  {paymentMethod === 'telegram_stars'
                    ? `${selectedPlan.priceStars * selectedPeriod.multiplier} ⭐`
                    : paymentMethod === 'ton'
                      ? t('billing.ton_price_after_invoice', 'Сумма будет показана после создания инвойса')
                      : paymentMethod === 'yookassa'
                        ? t('billing.yk_price_after_invoice', 'Сумма будет показана после создания инвойса')
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
                disabled={submitting || tonChecking || ykChecking}
              >
                {t('billing.button_cancel')}
              </button>

              <button
                type="button"
                className="btn"
                disabled={!selectedPlan.productCode || !paymentMethod || submitting || tonChecking || ykChecking}
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
              <h3 className="modal-title">{t('billing.payment_success_title', 'Оплата успешна')}</h3>
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
                {t('billing.payment_success_ok', 'Ок')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default Billing;
