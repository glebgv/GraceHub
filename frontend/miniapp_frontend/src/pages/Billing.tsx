import React, { useEffect, useState } from 'react';
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

// Соотношение Stars → TON (можно вынести в env или получать с backend)
const TON_PRICE_LITE = 0.3;
const TON_PRICE_PRO = 0.8;
const TON_PRICE_ENTERPRISE = 2.5;

const getTonPrice = (planCode: string): number => {
  const map: Record<string, number> = {
    lite: TON_PRICE_LITE,
    pro: TON_PRICE_PRO,
    enterprise: TON_PRICE_ENTERPRISE,
  };
  return map[planCode.toLowerCase()] || 0;
};

const Billing: React.FC<BillingProps> = ({ instanceId }) => {
  const { t } = useTranslation();
  const [plans, setPlans] = useState<SaasPlanDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedPlan, setSelectedPlan] = useState<SaasPlanDTO | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption | null>(periodOptions[0]);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('telegram_stars');

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [paymentResult, setPaymentResult] = useState<{
    planName: string;
    months: number;
  } | null>(null);

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

  const openPlanModal = (plan: SaasPlanDTO) => {
    setSelectedPlan(plan);
    setSelectedPeriod(periodOptions[0]);
    setPaymentMethod('telegram_stars');
    setSubmitError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedPlan(null);
    setSubmitError(null);
  };

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const pollTonStatus = async (invoiceId: number, timeoutMs: number = 120000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const st = await apiClient.getTonInvoiceStatus(invoiceId);

      if (st.status === 'paid' && st.period_applied) return st;
      if (st.status === 'failed') throw new Error(t('billing.payment_failed'));

      await sleep(2500);
    }
    throw new Error(t('billing.payment_failed'));
  };

  // UPDATED: prefer opening Tonkeeper link via external browser on Android Telegram
  // because Telegram in-app browser may lose deeplink query params.
  const openTonLink = (link: string) => {
    const tg = window.Telegram?.WebApp;

    // 1) Try Telegram openLink with "no instant view" option (some clients support it)
    try {
      (tg as any)?.openLink?.(link, { try_instant_view: false });
      return;
    } catch (e) {
      // ignore and fallback
    }

    // 2) Try plain tg.openLink
    try {
      tg?.openLink?.(link);
      return;
    } catch (e) {
      // ignore and fallback
    }

    // 3) Fallback: open new tab/window (often triggers external browser on Android)
    try {
      window.open(link, '_blank', 'noopener,noreferrer');
      return;
    } catch (e) {
      // ignore and fallback
    }

    // 4) Last resort
    window.location.href = link;
  };

  const handleCreateInvoice = async () => {
    if (!selectedPlan || !selectedPeriod) return;
    if (!selectedPlan.productCode) return;

    try {
      setSubmitting(true);
      setSubmitError(null);

      const resp = await apiClient.createBillingInvoice(instanceId, {
        plan_code: selectedPlan.planCode,
        periods: selectedPeriod.multiplier,
        payment_method: paymentMethod,
      });

      console.log('createBillingInvoice resp =', resp);
      console.log('Telegram.WebApp object =', window.Telegram?.WebApp);

      // Stars
      if (paymentMethod === 'telegram_stars') {
        const tg = window.Telegram?.WebApp;

        if (tg?.openInvoice) {
          tg.openInvoice(resp.invoice_link, (status: string) => {
            console.log('openInvoice status =', status);

            if (status === 'paid') {
              closeModal();
              setPaymentResult({
                planName: selectedPlan.planName,
                months: selectedPeriod.multiplier,
              });
            } else if (status === 'failed') {
              setSubmitError(t('billing.payment_failed'));
            } else if (status === 'cancelled') {
              // пользователь закрыл окно оплаты — ничего не делаем
            }
          });
        } else {
          console.warn('Telegram.WebApp.openInvoice is not available, fallback to window.open');
          window.open(resp.invoice_link, '_blank', 'noopener,noreferrer');
        }

        return;
      }

      // TON
      openTonLink(resp.invoice_link);

      const st = await pollTonStatus(resp.invoice_id, 120000);

      if (st.status === 'paid') {
        closeModal();
        setPaymentResult({
          planName: selectedPlan.planName,
          months: selectedPeriod.multiplier,
        });
      }
    } catch (e: any) {
      console.error('createBillingInvoice error', e);
      setSubmitError(e?.message || 'Failed to create invoice');
    } finally {
      setSubmitting(false);
    }
  };

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

      {isModalOpen && selectedPlan && selectedPeriod && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 420 }}
          >
            <div className="modal-header">
              <h3 className="modal-title">{t('billing.modal_title', { name: selectedPlan.planName })}</h3>
              <button type="button" className="modal-close" onClick={closeModal}>
                ✕
              </button>
            </div>

            <div className="modal-body">
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

              {/* Способ оплаты */}
              <div style={{ marginTop: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 500 }}>
                  {t('billing.payment_method_label', 'Способ оплаты')}
                </div>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => setPaymentMethod('telegram_stars')}
                    className={paymentMethod === 'telegram_stars' ? 'btn btn--secondary' : 'btn btn--ghost'}
                    style={{ flex: '1 1 0' }}
                    disabled={submitting}
                  >
                    {t('billing.payment_method_stars', 'Telegram Stars')}
                  </button>

                  <button
                    type="button"
                    onClick={() => setPaymentMethod('ton')}
                    className={paymentMethod === 'ton' ? 'btn btn--secondary' : 'btn btn--ghost'}
                    style={{ flex: '1 1 0' }}
                    disabled={submitting}
                  >
                    {t('billing.payment_method_ton', 'TON')}
                  </button>
                </div>

                {paymentMethod === 'ton' && (
                  <p style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
                    {t(
                      'billing.ton_hint',
                      'После нажатия "Выбрать" откроется браузер/кошелёк. Подтвердите перевод и вернитесь в Telegram.',
                    )}
                  </p>
                )}
              </div>

              {/* Выбор периода */}
              <div style={{ marginTop: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 500 }}>
                  {t('billing.choose_period_label')}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {periodOptions.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setSelectedPeriod(opt)}
                      className={opt.id === selectedPeriod.id ? 'btn btn--secondary' : 'btn btn--ghost'}
                      style={{ flex: '1 1 0' }}
                      disabled={submitting}
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

                <div style={{ marginTop: 8, fontSize: 13, opacity: 0.8 }}>
                  {t('billing.final_price_label')}
                </div>

                <div style={{ fontSize: 16, fontWeight: 600 }}>
                  {paymentMethod === 'telegram_stars'
                    ? `${selectedPlan.priceStars * selectedPeriod.multiplier} ⭐`
                    : `${(getTonPrice(selectedPlan.planCode) * selectedPeriod.multiplier).toFixed(2)} TON`}
                </div>

                {submitError && (
                  <p
                    style={{
                      marginTop: 8,
                      fontSize: 12,
                      color: 'var(--tg-color-error, #dc2626)',
                    }}
                  >
                    {submitError}
                  </p>
                )}
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={closeModal}
                disabled={submitting}
              >
                {t('billing.button_cancel')}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!selectedPlan.productCode || submitting}
                onClick={handleCreateInvoice}
              >
                {submitting ? t('billing.button_processing') : t('billing.button_choose')}
              </button>
            </div>
          </div>
        </div>
      )}

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
            style={{ maxWidth: 420 }}
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

            <div className="modal-body">
              <p style={{ marginBottom: 8 }}>
                {t('billing.payment_success_body', {
                  name: paymentResult.planName,
                  months: paymentResult.months,
                })}
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
