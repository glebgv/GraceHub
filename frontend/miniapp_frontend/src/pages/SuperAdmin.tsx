// src/pages/SuperAdmin.tsx
import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import type { MiniappPublicSettings } from '../api/client';

interface SuperAdminProps {
  onBack?: () => void;
}

const defaultSettings: MiniappPublicSettings = {
  singleTenant: {
    enabled: false,
    ownerTelegramId: null,
  },
  superadmins: [],
  payments: {
    enabled: {
      telegramStars: true,
      ton: true,
      yookassa: false,
    },
    ton: {
      network: 'testnet',
      walletAddress: '',
      apiBaseUrl: 'https://testnet.toncenter.com/api/v2',
      apiKey: '',
      checkDelaySeconds: 5,
      confirmationsRequired: 1,
      pricePerPeriodLite: 0.5,
      pricePerPeriodPro: 2.0,
      pricePerPeriodEnterprise: 5.0,
    },
    yookassa: {
      shopId: '',
      secretKey: '',
      returnUrl: '',
      testMode: true,
      priceRubLite: 199,
      priceRubPro: 499,
      priceRubEnterprise: 1999,
    },
  },
  instanceDefaults: {
    antifloodMaxUserMessagesPerMinute: 20,
    workerMaxFileMb: 10,
    maxInstancesPerUser: 3,
  },
};

function safeNumber(v: any, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function mergeDefaults(value: any): MiniappPublicSettings {
  const v = value || {};
  return {
    singleTenant: {
      enabled: !!v?.singleTenant?.enabled,
      ownerTelegramId:
        v?.singleTenant?.ownerTelegramId === null || v?.singleTenant?.ownerTelegramId === undefined
          ? null
          : safeNumber(v?.singleTenant?.ownerTelegramId, null as any),
    },
    superadmins: Array.isArray(v?.superadmins)
      ? v.superadmins.map((x: any) => safeNumber(x, 0)).filter((x: number) => x > 0)
      : [],
    payments: {
      enabled: {
        telegramStars: !!v?.payments?.enabled?.telegramStars,
        ton: !!v?.payments?.enabled?.ton,
        yookassa: !!v?.payments?.enabled?.yookassa,
      },
      ton: {
        network: v?.payments?.ton?.network === 'mainnet' ? 'mainnet' : 'testnet',
        walletAddress: String(v?.payments?.ton?.walletAddress ?? ''),
        apiBaseUrl: String(v?.payments?.ton?.apiBaseUrl ?? defaultSettings.payments.ton.apiBaseUrl),
        apiKey: String(v?.payments?.ton?.apiKey ?? ''),
        checkDelaySeconds: safeNumber(
          v?.payments?.ton?.checkDelaySeconds,
          defaultSettings.payments.ton.checkDelaySeconds,
        ),
        confirmationsRequired: safeNumber(
          v?.payments?.ton?.confirmationsRequired,
          defaultSettings.payments.ton.confirmationsRequired,
        ),
        pricePerPeriodLite: safeNumber(
          v?.payments?.ton?.pricePerPeriodLite,
          defaultSettings.payments.ton.pricePerPeriodLite,
        ),
        pricePerPeriodPro: safeNumber(
          v?.payments?.ton?.pricePerPeriodPro,
          defaultSettings.payments.ton.pricePerPeriodPro,
        ),
        pricePerPeriodEnterprise: safeNumber(
          v?.payments?.ton?.pricePerPeriodEnterprise,
          defaultSettings.payments.ton.pricePerPeriodEnterprise,
        ),
      },
      yookassa: {
        shopId: String(v?.payments?.yookassa?.shopId ?? ''),
        secretKey: String(v?.payments?.yookassa?.secretKey ?? ''),
        returnUrl: String(v?.payments?.yookassa?.returnUrl ?? ''),
        testMode:
          v?.payments?.yookassa?.testMode !== undefined
            ? !!v.payments.yookassa.testMode
            : defaultSettings.payments.yookassa.testMode,
        priceRubLite: safeNumber(
          v?.payments?.yookassa?.priceRubLite,
          defaultSettings.payments.yookassa.priceRubLite,
        ),
        priceRubPro: safeNumber(
          v?.payments?.yookassa?.priceRubPro,
          defaultSettings.payments.yookassa.priceRubPro,
        ),
        priceRubEnterprise: safeNumber(
          v?.payments?.yookassa?.priceRubEnterprise,
          defaultSettings.payments.yookassa.priceRubEnterprise,
        ),
      },
    },
    instanceDefaults: {
      antifloodMaxUserMessagesPerMinute: safeNumber(
        v?.instanceDefaults?.antifloodMaxUserMessagesPerMinute,
        defaultSettings.instanceDefaults.antifloodMaxUserMessagesPerMinute,
      ),
      workerMaxFileMb: safeNumber(
        v?.instanceDefaults?.workerMaxFileMb,
        defaultSettings.instanceDefaults.workerMaxFileMb,
      ),
      maxInstancesPerUser: safeNumber(
        v?.instanceDefaults?.maxInstancesPerUser,
        defaultSettings.instanceDefaults.maxInstancesPerUser,
      ),
    },
  };
}

const SuperAdmin: React.FC<SuperAdminProps> = ({ onBack }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [me, setMe] = useState<any>(null);
  const [form, setForm] = useState<MiniappPublicSettings>(defaultSettings);

  const isSuperadmin = useMemo(() => {
    const roles = me?.roles || [];
    return Array.isArray(roles) && roles.includes('superadmin');
  }, [me]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const [meData, settings] = await Promise.all([
          apiClient.getMe(),
          apiClient.getMiniappPublicSettings(),
        ]);

        if (cancelled) return;

        setMe(meData);
        setForm(mergeDefaults(settings));
        setError(null);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message || 'Load error');
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      // если single-tenant включён — запрещаем менять maxInstancesPerUser и шлюзы (как ты хотел по правилам UI)
      const normalized: MiniappPublicSettings = {
        ...form,
        instanceDefaults: {
          ...form.instanceDefaults,
          maxInstancesPerUser: form.singleTenant.enabled
            ? defaultSettings.instanceDefaults.maxInstancesPerUser
            : form.instanceDefaults.maxInstancesPerUser,
        },
        payments: form.singleTenant.enabled
          ? {
              ...form.payments,
              enabled: {
                telegramStars: form.payments.enabled.telegramStars,
                ton: false,
                yookassa: false,
              },
            }
          : form.payments,
      };

      await apiClient.setMiniappPublicSettings(normalized);
      alert('Saved');
      setError(null);
      setForm(normalized);
    } catch (e: any) {
      setError(e?.message || 'Save error');
    } finally {
      setSaving(false);
    }
  };

  const addSuperadmin = () => {
    const raw = prompt('Введите Telegram user_id суперадмина (число):');
    if (!raw) return;
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) {
      alert('Некорректный user_id');
      return;
    }
    setForm((prev) => ({
      ...prev,
      superadmins: Array.from(new Set([...(prev.superadmins || []), id])).sort((a, b) => a - b),
    }));
  };

  const removeSuperadmin = (id: number) => {
    if (!confirm(`Удалить суперадмина ${id}?`)) return;
    setForm((prev) => ({
      ...prev,
      superadmins: (prev.superadmins || []).filter((x) => x !== id),
    }));
  };

  if (loading) return <div className="card">Loading superadmin…</div>;

  if (!isSuperadmin) {
    return (
      <div className="card" style={{ color: 'var(--color-error)' }}>
        Forbidden: superadmin only
      </div>
    );
  }

  return (
    <div className="main-content">
      {/* Header card (sticky) */}
      <div className="card superadmin-sticky">
        <div className="card-header">
          <div className="card-title">Superadmin panel</div>

          {onBack && (
            <button type="button" className="btn btn--secondary btn--sm" onClick={onBack} disabled={saving}>
              ← Back
            </button>
          )}
        </div>

        <div style={{ paddingTop: 0 }}>
          {error && <div style={{ color: 'var(--color-error)', marginBottom: 10 }}>{error}</div>}

          <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
            <button className="btn btn--primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>

            <button
              className="btn btn--secondary"
              onClick={async () => {
                try {
                  const res = await apiClient.getManageHealth();
                  alert(`Manage health: ${res.status}`);
                } catch (e: any) {
                  alert(e?.message || 'Manage error');
                }
              }}
              disabled={saving}
            >
              Manage /health
            </button>
          </div>
        </div>
      </div>

      {/* Single tenant */}
      <div className="card">
        <div className="card-title">Single-tenant</div>

        <div className="list-item" style={{ justifyContent: 'flex-start', gap: 10 }}>
          <input
            type="checkbox"
            checked={form.singleTenant.enabled}
            onChange={(e) =>
              setForm((p) => ({ ...p, singleTenant: { ...p.singleTenant, enabled: e.target.checked } }))
            }
          />
          <div>Enable single-tenant mode</div>
        </div>

        <div className="form-group" style={{ padding: '0 var(--space-14) var(--space-14)' as any }}>
          <label className="form-label">Owner Telegram ID</label>
          <input
            className="form-control"
            type="number"
            disabled={!form.singleTenant.enabled}
            value={form.singleTenant.ownerTelegramId ?? ''}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                singleTenant: {
                  ...p.singleTenant,
                  ownerTelegramId: e.target.value === '' ? null : Number(e.target.value),
                },
              }))
            }
          />
          <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12 }}>
            UI сохраняет это в platform_settings. Для реального эффекта нужно будет применить на бекенде к settings/env.
          </div>
        </div>
      </div>

      {/* Superadmins */}
      <div className="card">
        <div className="card-title">Superadmins</div>

        <div style={{ padding: '0 var(--space-14) var(--space-14)' as any }}>
          <button className="btn btn--secondary" onClick={addSuperadmin}>
            Add superadmin
          </button>

          <div style={{ marginTop: 12 }}>
            {(form.superadmins || []).length === 0 ? (
              <div style={{ opacity: 0.7 }}>No superadmins configured in DB settings.</div>
            ) : (
              (form.superadmins || []).map((id) => (
                <div key={id} className="list-item">
                  <div>{id}</div>
                  <button className="btn btn--outline btn--sm" onClick={() => removeSuperadmin(id)}>
                    Remove
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Instance defaults */}
      <div className="card">
        <div className="card-title">Instance defaults</div>

        <div style={{ padding: '0 var(--space-14) var(--space-14)' as any }}>
          <div className="form-group">
            <label className="form-label">ANTIFLOOD_MAX_USER_MESSAGES_PER_MINUTE</label>
            <input
              className="form-control"
              type="number"
              value={form.instanceDefaults.antifloodMaxUserMessagesPerMinute}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: {
                    ...p.instanceDefaults,
                    antifloodMaxUserMessagesPerMinute: Number(e.target.value),
                  },
                }))
              }
            />
          </div>

          <div className="form-group">
            <label className="form-label">WORKER_MAX_FILE_MB</label>
            <input
              className="form-control"
              type="number"
              value={form.instanceDefaults.workerMaxFileMb}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: {
                    ...p.instanceDefaults,
                    workerMaxFileMb: Number(e.target.value),
                  },
                }))
              }
            />
          </div>

          <div className="form-group">
            <label className="form-label">MAX_INSTANCES_PER_USER</label>
            <input
              className="form-control"
              type="number"
              disabled={form.singleTenant.enabled}
              value={form.instanceDefaults.maxInstancesPerUser}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: {
                    ...p.instanceDefaults,
                    maxInstancesPerUser: Number(e.target.value),
                  },
                }))
              }
            />
            {form.singleTenant.enabled && (
              <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12 }}>
                Disabled in UI because single-tenant mode is enabled.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Payments */}
      <div className="card">
        <div className="card-title">Payments (UI)</div>

        <div style={{ padding: '0 var(--space-14) var(--space-14)' as any }}>
          <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12, marginBottom: 12 }}>
            Эти тумблеры сейчас влияют только на UI (что показывать в Billing). Для реального отключения нужно будет
            применить на бекенде, т.к. инвойсы создаются там.
          </div>

          <div className="list-item" style={{ justifyContent: 'flex-start', gap: 10 }}>
            <input
              type="checkbox"
              checked={form.payments.enabled.telegramStars}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  payments: { ...p.payments, enabled: { ...p.payments.enabled, telegramStars: e.target.checked } },
                }))
              }
            />
            <div>Telegram Stars</div>
          </div>

          <div className="list-item" style={{ justifyContent: 'flex-start', gap: 10 }}>
            <input
              type="checkbox"
              disabled={form.singleTenant.enabled}
              checked={form.payments.enabled.ton}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  payments: { ...p.payments, enabled: { ...p.payments.enabled, ton: e.target.checked } },
                }))
              }
            />
            <div>TON</div>
          </div>

          <div className="list-item" style={{ justifyContent: 'flex-start', gap: 10 }}>
            <input
              type="checkbox"
              disabled={form.singleTenant.enabled}
              checked={form.payments.enabled.yookassa}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  payments: { ...p.payments, enabled: { ...p.payments.enabled, yookassa: e.target.checked } },
                }))
              }
            />
            <div>YooKassa</div>
          </div>

          {/* TON settings */}
          {form.payments.enabled.ton && !form.singleTenant.enabled && (
            <div style={{ marginTop: 14 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>
                TON settings
              </div>

              <div className="form-group">
                <label className="form-label">TON_NETWORK</label>
                <select
                  className="form-control"
                  value={form.payments.ton.network}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, ton: { ...p.payments.ton, network: e.target.value as any } },
                    }))
                  }
                >
                  <option value="testnet">testnet</option>
                  <option value="mainnet">mainnet</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">TON_WALLET_ADDRESS</label>
                <input
                  className="form-control"
                  value={form.payments.ton.walletAddress}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, ton: { ...p.payments.ton, walletAddress: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="form-group">
                <label className="form-label">TON_API_BASE_URL</label>
                <input
                  className="form-control"
                  value={form.payments.ton.apiBaseUrl}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, ton: { ...p.payments.ton, apiBaseUrl: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="form-group">
                <label className="form-label">TON_API_KEY</label>
                <input
                  className="form-control"
                  value={form.payments.ton.apiKey}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, ton: { ...p.payments.ton, apiKey: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 160px' }}>
                  <div className="form-group">
                    <label className="form-label">TON_CHECK_DELAY_SECONDS</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.ton.checkDelaySeconds}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, checkDelaySeconds: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div style={{ flex: '1 1 160px' }}>
                  <div className="form-group">
                    <label className="form-label">TON_CONFIRMATIONS_REQUIRED</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.ton.confirmationsRequired}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, confirmationsRequired: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">TON_PRICE_PER_PERIOD_LITE</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.ton.pricePerPeriodLite}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, pricePerPeriodLite: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">TON_PRICE_PER_PERIOD_PRO</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.ton.pricePerPeriodPro}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, pricePerPeriodPro: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">TON_PRICE_PER_PERIOD_ENTERPRISE</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.ton.pricePerPeriodEnterprise}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, pricePerPeriodEnterprise: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* YooKassa settings */}
          {form.payments.enabled.yookassa && !form.singleTenant.enabled && (
            <div style={{ marginTop: 14 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>
                YooKassa settings
              </div>

              <div className="form-group">
                <label className="form-label">YOOKASSA_SHOP_ID</label>
                <input
                  className="form-control"
                  value={form.payments.yookassa.shopId}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, yookassa: { ...p.payments.yookassa, shopId: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="form-group">
                <label className="form-label">YOOKASSA_SECRET_KEY</label>
                <input
                  className="form-control"
                  value={form.payments.yookassa.secretKey}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, yookassa: { ...p.payments.yookassa, secretKey: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="form-group">
                <label className="form-label">YOOKASSA_RETURN_URL</label>
                <input
                  className="form-control"
                  value={form.payments.yookassa.returnUrl}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, yookassa: { ...p.payments.yookassa, returnUrl: e.target.value } },
                    }))
                  }
                />
              </div>

              <div className="list-item" style={{ justifyContent: 'flex-start', gap: 10 }}>
                <input
                  type="checkbox"
                  checked={form.payments.yookassa.testMode}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, yookassa: { ...p.payments.yookassa, testMode: e.target.checked } },
                    }))
                  }
                />
                <div>YOOKASSA_TEST_MODE</div>
              </div>

              <div className="flex gap-8" style={{ flexWrap: 'wrap', marginTop: 12 }}>
                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">YOOKASSA_PRICE_RUB_LITE</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.yookassa.priceRubLite}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, priceRubLite: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">YOOKASSA_PRICE_RUB_PRO</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.yookassa.priceRubPro}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, priceRubPro: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div style={{ flex: '1 1 140px' }}>
                  <div className="form-group">
                    <label className="form-label">YOOKASSA_PRICE_RUB_ENTERPRISE</label>
                    <input
                      className="form-control"
                      type="number"
                      value={form.payments.yookassa.priceRubEnterprise}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, priceRubEnterprise: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SuperAdmin;
