import React, { useEffect, useState } from 'react';
import { apiClient, SaasPlanDTO } from '../api/client';
import { useTranslation } from 'react-i18next';

interface BillingProps {
  instanceId: string;
}

const Billing: React.FC<BillingProps> = ({ instanceId }) => {
  const { t } = useTranslation();
  const [plans, setPlans] = useState<SaasPlanDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  if (loading) {
    return (
      <div style={{ padding: '12px' }}>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div className="loading-spinner" style={{ margin: '0 auto' }}></div>
          <p>Загрузка тарифов…</p>
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
          <p style={{ margin: 0 }}>Ошибка загрузки тарифов: {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px' }}>
      {plans.map((plan) => (
        <div key={plan.planCode} className="card">
          <div className="list-item">
            <div className="list-item-info">
              <div className="list-item-title">{plan.planName}</div>
              <div className="list-item-subtitle">
                {plan.periodDays} дней • до {plan.ticketsLimit} тикетов
              </div>
              <div style={{ marginTop: '4px', fontSize: '13px' }}>
                {plan.priceStars} ⭐
              </div>
            </div>
            <button
              className="btn"
              disabled={!plan.productCode}
              onClick={() => {
                // TODO: позже здесь будет create_invoice(productCode, instanceId)
              }}
            >
              Выбрать
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default Billing;

