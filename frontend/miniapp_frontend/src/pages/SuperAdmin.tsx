// src/pages/SuperAdmin.tsx
//
// NEW (FirstLaunch offer gating):
// - Добавлен блок настроек "Offer (FirstLaunch)" -> miniapp_public.offer.enabled + miniapp_public.offer.url
// - URL валидируется как https://
// - В save() проходит через нормализацию mergeDefaults/normalizeIds, как и остальная форма

import React, { useEffect, useMemo, useState } from 'react';

import { apiClient } from '../api/client';
import type { MiniappPublicSettings } from '../api/client';
import { useTranslation } from 'react-i18next';
import logoRed from '../assets/logo-red.png';

interface SuperAdminProps {
  onBack?: () => void;
}

const defaultSettings: MiniappPublicSettings = {
  singleTenant: {
    enabled: false,
    allowedUserIds: [],
  },
  superadmins: [],
  payments: {
    enabled: {
      telegramStars: true,
      ton: true,
      yookassa: false,
      stripe: false,
    },
    telegramStars: {
      priceStarsLite: 100,
      priceStarsPro: 300,
      priceStarsEnterprise: 999,
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
    stripe: {
      secretKey: '',
      publishableKey: '',
      webhookSecret: '',
      currency: 'usd',
      // NEW:
      successUrl: '',
      cancelUrl: '',
      priceUsdLite: 4.99,
      priceUsdPro: 9.99,
      priceUsdEnterprise: 29.99,
    },
  },
  // NEW: Offer gating (FirstLaunch)
  offer: {
    enabled: false,
    url: '',
  },
  instanceDefaults: {
    antifloodMaxUserMessagesPerMinute: 20,
    workerMaxFileMb: 10,
    maxInstancesPerUser: 3,
  },
};

const TON_MAINNET_DEFAULT_API = 'https://toncenter.com/api/v2';
const TON_TESTNET_DEFAULT_API = defaultSettings.payments.ton.apiBaseUrl;

function safeNumber(v: any, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeIds(list: any): number[] {
  if (!Array.isArray(list)) return [];
  return Array.from(
    new Set(list.map((x) => safeNumber(x, 0)).filter((x: number) => Number.isFinite(x) && x > 0)),
  ).sort((a, b) => a - b);
}

function mergeDefaults(value: any): MiniappPublicSettings {
  const v = value || {};

  // Миграция старого формата: ownerTelegramId -> allowedUserIds[0]
  const allowedUserIds =
    Array.isArray(v?.singleTenant?.allowedUserIds) && v.singleTenant.allowedUserIds.length > 0
      ? normalizeIds(v.singleTenant.allowedUserIds)
      : v?.singleTenant?.ownerTelegramId === null || v?.singleTenant?.ownerTelegramId === undefined
        ? []
        : normalizeIds([v.singleTenant.ownerTelegramId]);

  const offer = v?.offer || {};

  return {
    singleTenant: {
      enabled: !!v?.singleTenant?.enabled,
      allowedUserIds,
    },
    superadmins: Array.isArray(v?.superadmins)
      ? v.superadmins.map((x: any) => safeNumber(x, 0)).filter((x: number) => x > 0)
      : [],
    payments: {
      enabled: {
        telegramStars: !!v?.payments?.enabled?.telegramStars,
        ton: !!v?.payments?.enabled?.ton,
        yookassa: !!v?.payments?.enabled?.yookassa,
        stripe: !!v?.payments?.enabled?.stripe,
      },
      telegramStars: {
        priceStarsLite: safeNumber(
          v?.payments?.telegramStars?.priceStarsLite,
          defaultSettings.payments.telegramStars.priceStarsLite,
        ),
        priceStarsPro: safeNumber(
          v?.payments?.telegramStars?.priceStarsPro,
          defaultSettings.payments.telegramStars.priceStarsPro,
        ),
        priceStarsEnterprise: safeNumber(
          v?.payments?.telegramStars?.priceStarsEnterprise,
          defaultSettings.payments.telegramStars.priceStarsEnterprise,
        ),
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
        priceRubLite: safeNumber(v?.payments?.yookassa?.priceRubLite, defaultSettings.payments.yookassa.priceRubLite),
        priceRubPro: safeNumber(v?.payments?.yookassa?.priceRubPro, defaultSettings.payments.yookassa.priceRubPro),
        priceRubEnterprise: safeNumber(
          v?.payments?.yookassa?.priceRubEnterprise,
          defaultSettings.payments.yookassa.priceRubEnterprise,
        ),
      },
      stripe: {
        secretKey: String(v?.payments?.stripe?.secretKey ?? ''),
        publishableKey: String(v?.payments?.stripe?.publishableKey ?? ''),
        webhookSecret: String(v?.payments?.stripe?.webhookSecret ?? ''),
        currency: String(v?.payments?.stripe?.currency ?? 'usd'),
        // NEW:
        successUrl: String(v?.payments?.stripe?.successUrl ?? ''),
        cancelUrl: String(v?.payments?.stripe?.cancelUrl ?? ''),
        priceUsdLite: safeNumber(v?.payments?.stripe?.priceUsdLite, defaultSettings.payments.stripe.priceUsdLite),
        priceUsdPro: safeNumber(v?.payments?.stripe?.priceUsdPro, defaultSettings.payments.stripe.priceUsdPro),
        priceUsdEnterprise: safeNumber(
          v?.payments?.stripe?.priceUsdEnterprise,
          defaultSettings.payments.stripe.priceUsdEnterprise,
        ),
      },
    },
    // NEW: offer config
    offer: {
      enabled: !!offer?.enabled,
      url: String(offer?.url ?? ''),
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

/**
 * Детерминированный JSON stringify:
 * - рекурсивно сортирует ключи объектов
 * - не использует WeakSet (циклов в form быть не должно)
 */
function stableStringify(obj: any): string {
  const normalize = (v: any): any => {
    if (v === null || v === undefined) return v;
    if (typeof v !== 'object') return v;
    if (Array.isArray(v)) return v.map(normalize);

    const out: Record<string, any> = {};
    for (const k of Object.keys(v).sort()) out[k] = normalize(v[k]);
    return out;
  };

  return JSON.stringify(normalize(obj));
}

const TrashIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    style={{ display: 'block' }}
  >
    <path
      d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v10h-2V9Zm4 0h2v10h-2V9ZM6 7h12l-1 14H7L6 7Z"
      fill="currentColor"
    />
  </svg>
);

type BaseModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
};

const BaseModal: React.FC<BaseModalProps> = ({ open, title, onClose, children }) => {
  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 9999,
      }}
    >
      <div className="modal card" style={{ width: 'min(520px, 100%)' }}>
        <div className="card-header" style={{ justifyContent: 'space-between' }}>
          <div className="card-title">{title}</div>
          <button type="button" className="btn btn--secondary btn--sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div style={{ padding: '0 var(--space-14) var(--space-14)' as any }}>{children}</div>
      </div>
    </div>
  );
};

type InfoModalProps = {
  open: boolean;
  title: string;
  text?: string;
  onClose: () => void;
};

const InfoModal: React.FC<InfoModalProps> = ({ open, title, text, onClose }) => {
  return (
    <BaseModal open={open} title={title} onClose={onClose}>
      {text ? <div style={{ marginBottom: 12, opacity: 0.9 }}>{text}</div> : null}
      <div className="flex gap-8" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn--primary" onClick={onClose}>
          OK
        </button>
      </div>
    </BaseModal>
  );
};

type ConfirmExitModalProps = {
  open: boolean;
  onExit: () => void;
  onStay: () => void;
};

const ConfirmExitModal: React.FC<ConfirmExitModalProps> = ({ open, onExit, onStay }) => {
  return (
    <BaseModal open={open} title="Подтверждение" onClose={onStay}>
      <div style={{ marginBottom: 12, opacity: 0.9 }}>У вас несохраненные изменения. Выйти?</div>
      <div className="flex gap-8" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-secondary" onClick={onStay}>
          Назад
        </button>
        <button type="button" className="btn btn-primary" onClick={onExit}>
          Выход
        </button>
      </div>
    </BaseModal>
  );
};

type ConfirmDeleteModalProps = {
  open: boolean;
  title?: string;
  text?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  open,
  title = 'Подтверждение',
  text = 'Удалить?',
  confirmText = 'Удалить',
  cancelText = 'Отмена',
  danger = true,
  onConfirm,
  onCancel,
}) => {
  return (
    <BaseModal open={open} title={title} onClose={onCancel}>
      <div style={{ marginBottom: 12, opacity: 0.9 }}>{text}</div>
      <div className="flex gap-8" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          {cancelText}
        </button>
        <button type="button" className={danger ? 'btn btn-danger' : 'btn btn-primary'} onClick={onConfirm}>
          {confirmText}
        </button>
      </div>
    </BaseModal>
  );
};

function isHttpsUrl(s: string): boolean {
  try {
    const u = new URL(s);
    return u.protocol === 'https:';
  } catch {
    return false;
  }
}

function isTonFriendlyAddressLike(s: string): boolean {
  const v = (s || '').trim();
  if (!v) return false;
  if (v.length < 46 || v.length > 60) return false;
  return /^[A-Za-z0-9_-]+$/.test(v);
}

/**
 * Мини-слайдер (переключатель) без зависимости от CSS проекта:
 * - размер компактный
 * - кликабелен по всей области
 * - поддерживает disabled
 */
const MiniSwitch: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  ariaLabel: string;
}> = ({ checked, onChange, disabled, ariaLabel }) => {
  const w = 34;
  const h = 20;
  const pad = 2;
  const knob = h - pad * 2;

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-pressed={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      style={{
        width: w,
        height: h,
        borderRadius: 999,
        border: '1px solid rgba(0,0,0,0.12)',
        background: checked ? '#2196F3' : 'rgba(0,0,0,0.12)',
        padding: 0,
        position: 'relative',
        outline: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        flex: '0 0 auto',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: pad,
          left: checked ? w - pad - knob : pad,
          width: knob,
          height: knob,
          borderRadius: 999,
          background: '#fff',
          boxShadow: '0 1px 2px rgba(0,0,0,0.20)',
          transition: 'left 120ms ease',
        }}
      />
    </button>
  );
};

const SuperAdmin: React.FC<SuperAdminProps> = ({ onBack }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [me, setMe] = useState<any>(null);

  const [form, setForm] = useState<MiniappPublicSettings>(defaultSettings);
  const [initialSnapshot, setInitialSnapshot] = useState(stableStringify(defaultSettings));

  const [newOwnerId, setNewOwnerId] = useState('');
  const [addOwnerOpen, setAddOwnerOpen] = useState(false);

  const [savedModalOpen, setSavedModalOpen] = useState(false);
  const [confirmExitOpen, setConfirmExitOpen] = useState(false);

  const [addSuperadminOpen, setAddSuperadminOpen] = useState(false);
  const [addSuperadminValue, setAddSuperadminValue] = useState('');

  const [paymentErrors, setPaymentErrors] = useState<Record<string, string>>({});
  const [offerErrors, setOfferErrors] = useState<Record<string, string>>({});

  // Confirm delete modal (shared for owners + superadmins)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<null | { kind: 'superadmin'; id: number } | { kind: 'owner'; id: number }>(
    null,
  );

  const isSuperadmin = useMemo(() => {
    const roles = me?.roles || [];
    return Array.isArray(roles) && roles.includes('superadmin');
  }, [me]);

  const dirty = useMemo(() => stableStringify(form) !== initialSnapshot, [form, initialSnapshot]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const [meData, settings] = await Promise.all([apiClient.getMe(), apiClient.getMiniappPublicSettings()]);
        if (cancelled) return;

        const merged = mergeDefaults(settings);

        // Safety: если single-tenant включён — в форме принудительно считаем payments выключенными
        const safeMerged: MiniappPublicSettings = merged.singleTenant.enabled
          ? {
              ...merged,
              payments: {
                ...merged.payments,
                enabled: {
                  telegramStars: false,
                  ton: false,
                  yookassa: false,
                  stripe: false,
                },
              },
            }
          : merged;

        setMe(meData);
        setForm(safeMerged);
        setInitialSnapshot(stableStringify(safeMerged));
        setError(null);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message || 'Load error');
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const validatePayments = (v: MiniappPublicSettings): Record<string, string> => {
    const errs: Record<string, string> = {};

    if (v.payments.enabled.ton) {
      const w = (v.payments.ton.walletAddress || '').trim();
      if (!isTonFriendlyAddressLike(w)) errs.ton_wallet = 'Некорректный TON-адрес (friendly).';

      const api = (v.payments.ton.apiBaseUrl || '').trim();
      if (!isHttpsUrl(api)) errs.ton_api = 'TON API URL должен начинаться с https://';

      const conf = Number(v.payments.ton.confirmationsRequired);
      if (!Number.isFinite(conf) || conf < 1) errs.ton_confirmations = 'Confirmations ≥ 1.';

      const delay = Number(v.payments.ton.checkDelaySeconds);
      if (!Number.isFinite(delay) || delay < 1) errs.ton_delay = 'Delay ≥ 1 сек.';
    }

    if (v.payments.enabled.yookassa) {
      const ret = (v.payments.yookassa.returnUrl || '').trim();
      if (!isHttpsUrl(ret)) errs.yk_return = 'Return URL должен начинаться с https://';
    }

    // NEW: Stripe redirects
    if (v.payments.enabled.stripe) {
      const s = (v.payments.stripe.successUrl || '').trim();
      const c = (v.payments.stripe.cancelUrl || '').trim();

      if (!s) errs.stripe_success_url = 'Stripe successUrl обязателен.';
      else if (!isHttpsUrl(s)) errs.stripe_success_url = 'Stripe successUrl должен начинаться с https://';

      if (!c) errs.stripe_cancel_url = 'Stripe cancelUrl обязателен.';
      else if (!isHttpsUrl(c)) errs.stripe_cancel_url = 'Stripe cancelUrl должен начинаться с https://';
    }

    return errs;
  };

  const validateOffer = (v: MiniappPublicSettings): Record<string, string> => {
    const errs: Record<string, string> = {};
    const enabled = !!v.offer?.enabled;
    const url = String(v.offer?.url ?? '').trim();

    if (enabled) {
      if (!url) errs.offer_url = 'URL оферты обязателен.';
      else if (!isHttpsUrl(url)) errs.offer_url = 'URL оферты должен начинаться с https://';
    }

    return errs;
  };

  const save = async () => {
    setSaving(true);
    try {
      const normalized: MiniappPublicSettings = {
        ...form,
        singleTenant: {
          ...form.singleTenant,
          allowedUserIds: normalizeIds(form.singleTenant.allowedUserIds),
        },
        offer: {
          enabled: !!form.offer?.enabled,
          url: String(form.offer?.url ?? ''),
        },
        instanceDefaults: {
          ...form.instanceDefaults,
          maxInstancesPerUser: form.singleTenant.enabled
            ? defaultSettings.instanceDefaults.maxInstancesPerUser
            : form.instanceDefaults.maxInstancesPerUser,
        },
        // В single-tenant режиме все платежные шлюзы выключены и не настраиваются
        payments: form.singleTenant.enabled
          ? {
              ...form.payments,
              enabled: {
                telegramStars: false,
                ton: false,
                yookassa: false,
                stripe: false,
              },
            }
          : form.payments,
      };

      const payErrs = validatePayments(normalized);
      setPaymentErrors(payErrs);

      const offErrs = validateOffer(normalized);
      setOfferErrors(offErrs);

      const hasErrors = [...Object.keys(payErrs), ...Object.keys(offErrs)].some((k) => {
        const v = (payErrs as any)[k] ?? (offErrs as any)[k];
        return !!v;
      });

      if (hasErrors) {
        setError('Исправь ошибки в настройках (Payments / Offer).');
        return;
      }

      await apiClient.setMiniappPublicSettings(normalized);
      setError(null);
      setForm(normalized);
      setInitialSnapshot(stableStringify(normalized));
      setSavedModalOpen(true);
    } catch (e: any) {
      setError(e?.message || 'Save error');
    } finally {
      setSaving(false);
    }
  };

  const addOwnerId = () => {
    const raw = newOwnerId.trim();
    if (!raw) return;

    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) {
      alert('Некорректный user_id');
      return;
    }

    setForm((prev) => ({
      ...prev,
      singleTenant: {
        ...prev.singleTenant,
        allowedUserIds: Array.from(new Set([...(prev.singleTenant.allowedUserIds || []), id])).sort((a, b) => a - b),
      },
    }));
    setNewOwnerId('');
  };

  const requestDeleteOwner = (id: number) => {
    setPendingDelete({ kind: 'owner', id });
    setConfirmDeleteOpen(true);
  };

  const requestDeleteSuperadmin = (id: number) => {
    setPendingDelete({ kind: 'superadmin', id });
    setConfirmDeleteOpen(true);
  };

  const confirmDelete = () => {
    if (!pendingDelete) {
      setConfirmDeleteOpen(false);
      return;
    }

    if (pendingDelete.kind === 'superadmin') {
      const id = pendingDelete.id;
      setForm((prev) => ({
        ...prev,
        superadmins: (prev.superadmins || []).filter((x) => x !== id),
      }));
    }

    if (pendingDelete.kind === 'owner') {
      const id = pendingDelete.id;
      setForm((prev) => ({
        ...prev,
        singleTenant: {
          ...prev.singleTenant,
          allowedUserIds: (prev.singleTenant.allowedUserIds || []).filter((x) => x !== id),
        },
      }));
    }

    setConfirmDeleteOpen(false);
    setPendingDelete(null);
  };

  const openAddSuperadmin = () => {
    setAddSuperadminValue('');
    setAddSuperadminOpen(true);
  };

  const submitAddSuperadmin = () => {
    const raw = addSuperadminValue.trim();
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

    setAddSuperadminOpen(false);
    setAddSuperadminValue('');
  };

  const openAddOwner = () => {
    setNewOwnerId('');
    setAddOwnerOpen(true);
  };

  const submitAddOwner = () => {
    addOwnerId();
    const raw = newOwnerId.trim();
    const id = Number(raw);
    if (raw && Number.isFinite(id) && id > 0) setAddOwnerOpen(false);
  };

  const handleBack = () => {
    if (!onBack) return;
    if (dirty) {
      setConfirmExitOpen(true);
      return;
    }
    onBack();
  };

  if (loading) return <div className="card">Loading superadmin…</div>;

  if (!isSuperadmin) {
    return <div className="card" style={{ color: 'var(--color-error)' }}>Forbidden: superadmin only</div>;
  }

  const confirmTitle =
    pendingDelete?.kind === 'superadmin'
      ? t('superAdmin.confirm_delete_superadmin_title')
      : pendingDelete?.kind === 'owner'
        ? t('superAdmin.confirm_delete_owner_title')
        : t('superAdmin.confirm_title');

  const confirmText =
    pendingDelete?.kind === 'superadmin'
      ? t('superAdmin.confirm_delete_superadmin_text', { id: pendingDelete.id })
      : pendingDelete?.kind === 'owner'
        ? t('superAdmin.confirm_delete_owner_text', { id: pendingDelete.id })
        : t('superAdmin.confirm_delete_text');

  return (
    <div style={{ padding: 12, paddingBottom: 72 }}>
      {/* Header */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <img src={logoRed} alt="GraceHub" style={{ width: 32, height: 32, borderRadius: 10 }} />
            <span style={{ fontSize: 22, fontWeight: 600 }}>GraceHub Admin Panel</span>
          </div>
        </div>
      </div>

      <InfoModal
        open={savedModalOpen}
        title={t('superAdmin.saved_title')}
        text={t('superAdmin.saved_text')}
        onClose={() => setSavedModalOpen(false)}
      />

      <ConfirmExitModal
        open={confirmExitOpen}
        onStay={() => setConfirmExitOpen(false)}
        onExit={() => {
          setConfirmExitOpen(false);
          onBack?.();
        }}
      />

      <ConfirmDeleteModal
        open={confirmDeleteOpen}
        title={confirmTitle}
        text={confirmText}
        confirmText={t('superAdmin.delete')}
        cancelText={t('superAdmin.cancel')}
        danger
        onCancel={() => {
          setConfirmDeleteOpen(false);
          setPendingDelete(null);
        }}
        onConfirm={confirmDelete}
      />

      <BaseModal
        open={addOwnerOpen}
        title={t('superAdmin.add_owner_title')}
        onClose={() => setAddOwnerOpen(false)}
      >
        <div className="form-group">
          <label className="form-label">Telegram user_id</label>
          <input
            className="form-input"
            type="number"
            value={newOwnerId}
            onChange={(e) => setNewOwnerId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                submitAddOwner();
              }
            }}
            placeholder={t('superAdmin.owner_user_id_placeholder')}
          />
        </div>

        <div className="flex gap-8" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={() => setAddOwnerOpen(false)}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={submitAddOwner}>
            Add
          </button>
        </div>
      </BaseModal>

      <BaseModal open={addSuperadminOpen} title={t('superAdmin.add_superadmin_title')} onClose={() => setAddSuperadminOpen(false)}>
        <div className="form-group">
          <label className="form-label">Telegram user_id</label>
          <input
            className="form-input"
            type="number"
            value={addSuperadminValue}
            onChange={(e) => setAddSuperadminValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                submitAddSuperadmin();
              }
            }}
            placeholder={t('superAdmin.telegram_user_id_placeholder_example')}
          />
        </div>
        <div className="flex gap-8" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={() => setAddSuperadminOpen(false)}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={submitAddSuperadmin}>
            Add
          </button>
        </div>
      </BaseModal>

      <div className="card">
        <div className="card-header">
          <div className="card-title">Superadmin panel</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {onBack && (
              <button type="button" className="btn btn-secondary" onClick={handleBack} disabled={saving}>
                ← Back
              </button>
            )}
          </div>
        </div>

        {dirty && (
          <div className="card" style={{ marginTop: 8, marginBottom: 8, position: 'sticky', top: 8, zIndex: 50 }}>
            <button className="btn btn-primary btn-block" type="button" onClick={save} disabled={saving}>
              💾 Save
            </button>
          </div>
        )}

        {error && (
          <div
            className="card"
            style={{
              background: 'rgba(255, 51, 51, 0.1)',
              borderColor: 'rgba(255, 51, 51, 0.3)',
              marginTop: 8,
            }}
          >
            <p style={{ margin: 0, color: 'var(--tg-color-text)' }}>{error}</p>
          </div>
        )}

        {/* Offer (FirstLaunch) */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Offer (FirstLaunch)</h3>

          <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <label className="form-label" style={{ marginBottom: 0 }}>
              Require offer acceptance
            </label>
            <MiniSwitch
              checked={!!form.offer?.enabled}
              disabled={saving}
              ariaLabel="Toggle offer gating"
              onChange={(checked) => {
                setForm((p) => ({
                  ...p,
                  offer: {
                    enabled: checked,
                    url: String(p.offer?.url ?? ''),
                  },
                }));
                setOfferErrors((prev) => ({ ...prev, offer_url: '' }));
              }}
            />
          </div>

          {form.offer?.enabled && (
            <div style={{ marginTop: 8 }}>
              <div className="form-group">
                <label className="form-label">Offer URL (https)</label>
                <input
                  className="form-input"
                  value={form.offer?.url ?? ''}
                  placeholder="https://your-domain/offer"
                  onChange={(e) => {
                    const v = e.target.value;
                    setForm((p) => ({
                      ...p,
                      offer: { enabled: !!p.offer?.enabled, url: v },
                    }));
                    setOfferErrors((prev) => ({ ...prev, offer_url: '' }));
                  }}
                  onBlur={() => {
                    const v = String(form.offer?.url ?? '').trim();
                    setOfferErrors((prev) => ({
                      ...prev,
                      offer_url: !v ? 'URL оферты обязателен.' : isHttpsUrl(v) ? '' : 'URL оферты должен начинаться с https://',
                    }));
                  }}
                />
                {offerErrors.offer_url ? (
                  <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                    {offerErrors.offer_url}
                  </small>
                ) : null}
              </div>

              <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12 }}>
                {t('superAdmin.firstLaunch_offer_block_hint')}
              </div>
            </div>
          )}
        </div>

        {/* Single-tenant */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Single-tenant</h3>

          <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <label className="form-label" style={{ marginBottom: 0 }}>
              Enable single-tenant mode
            </label>
            <MiniSwitch
              checked={form.singleTenant.enabled}
              disabled={saving}
              ariaLabel="Toggle single-tenant"
              onChange={(checked) => {
                setForm((p) => {
                  if (checked) {
                    return {
                      ...p,
                      singleTenant: { ...p.singleTenant, enabled: true },
                      payments: {
                        ...p.payments,
                        enabled: {
                          telegramStars: false,
                          ton: false,
                          yookassa: false,
                          stripe: false,
                        },
                      },
                    };
                  }
                  return {
                    ...p,
                    singleTenant: { ...p.singleTenant, enabled: false },
                  };
                });
                setPaymentErrors({});
              }}
            />
          </div>

          {form.singleTenant.enabled && (
            <>
              <div className="form-group" style={{ marginTop: 8 }}>
                <label className="form-label">Owner Telegram IDs</label>
                <button className="btn btn-secondary" type="button" onClick={openAddOwner} disabled={saving}>
                  Add
                </button>

                <div style={{ marginTop: 12 }}>
                  {(form.singleTenant.allowedUserIds || []).length === 0 ? (
                    <div style={{ opacity: 0.7 }}>No IDs configured.</div>
                  ) : (
                    (form.singleTenant.allowedUserIds || []).map((id) => (
                      <div
                        key={id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 10,
                          padding: '8px 0',
                          borderBottom: '1px solid rgba(0,0,0,0.06)',
                        }}
                      >
                        <div>{id}</div>
                        <button
                          type="button"
                          className="btn btn-outline"
                          onClick={() => requestDeleteOwner(id)}
                          title={`Удалить ${id}`}
                          aria-label={`Удалить ${id}`}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12 }}>
                  {t('superAdmin.single_tenant_allowlist_hint')}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Superadmins */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Superadmins</h3>

          <button className="btn btn-secondary" onClick={openAddSuperadmin} type="button" disabled={saving}>
            Add superadmin
          </button>

          <div style={{ marginTop: 12 }}>
            {(form.superadmins || []).length === 0 ? (
              <div style={{ opacity: 0.7 }}>No superadmins configured in DB settings.</div>
            ) : (
              (form.superadmins || []).map((id) => (
                <div
                  key={id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    padding: '8px 0',
                    borderBottom: '1px solid rgba(0,0,0,0.06)',
                  }}
                >
                  <div>{id}</div>
                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => requestDeleteSuperadmin(id)}
                    title={`Удалить ${id}`}
                    aria-label={`Удалить ${id}`}
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Instance defaults */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Instance defaults</h3>

          <div className="form-group">
            <label className="form-label">{t('superAdmin.antiflood_limit_hint')}</label>
            <input
              className="form-input"
              type="number"
              value={form.instanceDefaults.antifloodMaxUserMessagesPerMinute}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: { ...p.instanceDefaults, antifloodMaxUserMessagesPerMinute: Number(e.target.value) },
                }))
              }
            />
          </div>

          <div className="form-group">
            <label className="form-label">{t('superAdmin.attachments_limit_mb_hint')}</label>
            <input
              className="form-input"
              type="number"
              value={form.instanceDefaults.workerMaxFileMb}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: { ...p.instanceDefaults, workerMaxFileMb: Number(e.target.value) },
                }))
              }
            />
          </div>

          <div className="form-group">
            <label className="form-label">{t('superAdmin.bots_limit_hint')}</label>
            <input
              className="form-input"
              type="number"
              disabled={form.singleTenant.enabled}
              value={form.instanceDefaults.maxInstancesPerUser}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  instanceDefaults: { ...p.instanceDefaults, maxInstancesPerUser: Number(e.target.value) },
                }))
              }
            />
          </div>
        </div>

        {/* Payments */}
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Payments (UI)</h3>

          {form.singleTenant.enabled ? (
            <div
              style={{
                padding: '10px 12px',
                borderRadius: 10,
                background: 'rgba(33, 150, 243, 0.12)',
                border: '1px solid rgba(33, 150, 243, 0.25)',
                color: 'var(--tg-color-text)',
                fontSize: 13,
                lineHeight: 1.35,
              }}
            >
              {t('superAdmin.single_tenant_payments_disabled_hint')}
            </div>
          ) : (
            <>
              {/* Telegram Stars */}
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>
                  Telegram Stars
                </label>
                <MiniSwitch
                  checked={form.payments.enabled.telegramStars}
                  disabled={saving}
                  ariaLabel="Toggle Telegram Stars"
                  onChange={(checked) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, enabled: { ...p.payments.enabled, telegramStars: checked } },
                    }))
                  }
                />
              </div>

              {form.payments.enabled.telegramStars && (
                <div style={{ marginTop: 8 }}>
                  <div className="form-group">
                    <label className="form-label">Price Lite (Stars)</label>
                    <input
                      className="form-input"
                      type="number"
                      min={0}
                      value={form.payments.telegramStars.priceStarsLite}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            telegramStars: { ...p.payments.telegramStars, priceStarsLite: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Pro (Stars)</label>
                    <input
                      className="form-input"
                      type="number"
                      min={0}
                      value={form.payments.telegramStars.priceStarsPro}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            telegramStars: { ...p.payments.telegramStars, priceStarsPro: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Ent (Stars)</label>
                    <input
                      className="form-input"
                      type="number"
                      min={0}
                      value={form.payments.telegramStars.priceStarsEnterprise}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            telegramStars: {
                              ...p.payments.telegramStars,
                              priceStarsEnterprise: Number(e.target.value),
                            },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              )}

              {/* TON */}
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>
                  TON
                </label>
                <MiniSwitch
                  checked={form.payments.enabled.ton}
                  disabled={saving}
                  ariaLabel="Toggle TON payments"
                  onChange={(checked) => {
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, enabled: { ...p.payments.enabled, ton: checked } },
                    }));
                    setPaymentErrors((prev) => {
                      const n = { ...prev };
                      Object.keys(n)
                        .filter((k) => k.startsWith('ton_'))
                        .forEach((k) => delete n[k]);
                      return n;
                    });
                  }}
                />
              </div>

              {form.payments.enabled.ton && (
                <div style={{ marginTop: 8 }}>
                  <div className="form-group">
                    <label className="form-label">Network</label>
                    <select
                      className="form-select"
                      value={form.payments.ton.network}
                      onChange={(e) => {
                        const next = e.target.value as any;
                        setForm((p) => {
                          const prevNet = p.payments.ton.network;
                          const prevApi = (p.payments.ton.apiBaseUrl || '').trim();
                          const shouldAutoSwitchApi =
                            (prevNet === 'testnet' && prevApi === TON_TESTNET_DEFAULT_API) ||
                            (prevNet === 'mainnet' && prevApi === TON_MAINNET_DEFAULT_API);

                          return {
                            ...p,
                            payments: {
                              ...p.payments,
                              ton: {
                                ...p.payments.ton,
                                network: next,
                                apiBaseUrl: shouldAutoSwitchApi
                                  ? next === 'mainnet'
                                    ? TON_MAINNET_DEFAULT_API
                                    : TON_TESTNET_DEFAULT_API
                                  : p.payments.ton.apiBaseUrl,
                              },
                            },
                          };
                        });

                        setPaymentErrors((prev) => ({ ...prev, ton_api: '' }));
                      }}
                    >
                      <option value="testnet">Testnet</option>
                      <option value="mainnet">Mainnet</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Wallet</label>
                    <input
                      className="form-input"
                      value={form.payments.ton.walletAddress}
                      placeholder="0QC3VqDed0SODLgoelsv0oV3iBjUOKJuQjXdWhDENohmtW"
                      onChange={(e) => {
                        const v = e.target.value;
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, walletAddress: v } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, ton_wallet: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.ton.walletAddress || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          ton_wallet: isTonFriendlyAddressLike(v) ? '' : 'Некорректный TON-адрес (friendly).',
                        }));
                      }}
                    />
                    {paymentErrors.ton_wallet ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.ton_wallet}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">API URL</label>
                    <input
                      className="form-input"
                      value={form.payments.ton.apiBaseUrl}
                      placeholder="https://testnet.toncenter.com/api/v2"
                      onChange={(e) => {
                        const v = e.target.value;
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, apiBaseUrl: v } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, ton_api: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.ton.apiBaseUrl || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          ton_api: isHttpsUrl(v) ? '' : 'TON API URL должен начинаться с https://',
                        }));
                      }}
                    />
                    {paymentErrors.ton_api ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.ton_api}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      API key <small style={{ opacity: 0.7 }}>(необязательно)</small>
                    </label>
                    <input
                      className="form-input"
                      value={form.payments.ton.apiKey}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, apiKey: e.target.value } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Delay (sec)</label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      value={form.payments.ton.checkDelaySeconds}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, checkDelaySeconds: n } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, ton_delay: '' }));
                      }}
                      onBlur={() => {
                        const n = Number(form.payments.ton.checkDelaySeconds);
                        setPaymentErrors((prev) => ({
                          ...prev,
                          ton_delay: Number.isFinite(n) && n >= 1 ? '' : 'Delay ≥ 1 сек.',
                        }));
                      }}
                    />
                    {paymentErrors.ton_delay ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.ton_delay}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Confirmations</label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      value={form.payments.ton.confirmationsRequired}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, confirmationsRequired: n } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, ton_confirmations: '' }));
                      }}
                      onBlur={() => {
                        const n = Number(form.payments.ton.confirmationsRequired);
                        setPaymentErrors((prev) => ({
                          ...prev,
                          ton_confirmations: Number.isFinite(n) && n >= 1 ? '' : 'Confirmations ≥ 1.',
                        }));
                      }}
                    />
                    {paymentErrors.ton_confirmations ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.ton_confirmations}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Lite (TON)</label>
                    <input
                      className="form-input"
                      type="number"
                      value={form.payments.ton.pricePerPeriodLite}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, pricePerPeriodLite: Number(e.target.value) } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Pro (TON)</label>
                    <input
                      className="form-input"
                      type="number"
                      value={form.payments.ton.pricePerPeriodPro}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, ton: { ...p.payments.ton, pricePerPeriodPro: Number(e.target.value) } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Ent (TON)</label>
                    <input
                      className="form-input"
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
              )}

              {/* YooKassa */}
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>
                  YooKassa
                </label>
                <MiniSwitch
                  checked={form.payments.enabled.yookassa}
                  disabled={saving}
                  ariaLabel="Toggle YooKassa payments"
                  onChange={(checked) =>
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, enabled: { ...p.payments.enabled, yookassa: checked } },
                    }))
                  }
                />
              </div>

              {form.payments.enabled.yookassa && (
                <div style={{ marginTop: 8 }}>
                  <div className="form-group">
                    <label className="form-label">Shop ID</label>
                    <input
                      className="form-input"
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
                    <label className="form-label">Secret</label>
                    <input
                      className="form-input"
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
                    <label className="form-label">Return URL</label>
                    <input
                      className="form-input"
                      value={form.payments.yookassa.returnUrl}
                      placeholder="https://..."
                      onChange={(e) => {
                        const v = e.target.value;
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, yookassa: { ...p.payments.yookassa, returnUrl: v } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, yk_return: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.yookassa.returnUrl || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          yk_return: isHttpsUrl(v) ? '' : 'Return URL должен начинаться с https://',
                        }));
                      }}
                    />
                    {paymentErrors.yk_return ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.yk_return}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Lite (RUB)</label>
                    <input
                      className="form-input"
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

                  <div className="form-group">
                    <label className="form-label">Price Pro (RUB)</label>
                    <input
                      className="form-input"
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

                  <div className="form-group">
                    <label className="form-label">Price Ent (RUB)</label>
                    <input
                      className="form-input"
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
              )}

              {/* Stripe */}
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>
                  Stripe
                </label>
                <MiniSwitch
                  checked={form.payments.enabled.stripe}
                  disabled={saving}
                  ariaLabel="Toggle Stripe payments"
                  onChange={(checked) => {
                    setForm((p) => ({
                      ...p,
                      payments: { ...p.payments, enabled: { ...p.payments.enabled, stripe: checked } },
                    }));
                    setPaymentErrors((prev) => {
                      const n = { ...prev };
                      Object.keys(n)
                        .filter((k) => k.startsWith('stripe_'))
                        .forEach((k) => delete n[k]);
                      return n;
                    });
                  }}
                />
              </div>

              {form.payments.enabled.stripe && (
                <div style={{ marginTop: 8 }}>
                  <div className="form-group">
                    <label className="form-label">Secret Key</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.secretKey}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, secretKey: e.target.value } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Publishable Key</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.publishableKey}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, publishableKey: e.target.value },
                          },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Webhook Secret</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.webhookSecret}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, webhookSecret: e.target.value } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Currency (e.g., usd)</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.currency}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, currency: e.target.value.toLowerCase() },
                          },
                        }))
                      }
                    />
                  </div>

                  {/* NEW */}
                  <div className="form-group">
                    <label className="form-label">Success URL</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.successUrl || ''}
                      placeholder="https://your-domain/miniapp/billing/success"
                      onChange={(e) => {
                        const v = e.target.value;
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, successUrl: v } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, stripe_success_url: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.stripe.successUrl || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          stripe_success_url: !v
                            ? 'Stripe successUrl обязателен.'
                            : isHttpsUrl(v)
                              ? ''
                              : 'Stripe successUrl должен начинаться с https://',
                        }));
                      }}
                    />
                    {paymentErrors.stripe_success_url ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.stripe_success_url}
                      </small>
                    ) : null}
                  </div>

                  {/* NEW */}
                  <div className="form-group">
                    <label className="form-label">Cancel URL</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.cancelUrl || ''}
                      placeholder="https://your-domain/miniapp/billing/cancel"
                      onChange={(e) => {
                        const v = e.target.value;
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, cancelUrl: v } },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, stripe_cancel_url: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.stripe.cancelUrl || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          stripe_cancel_url: !v
                            ? 'Stripe cancelUrl обязателен.'
                            : isHttpsUrl(v)
                              ? ''
                              : 'Stripe cancelUrl должен начинаться с https://',
                        }));
                      }}
                    />
                    {paymentErrors.stripe_cancel_url ? (
                      <small style={{ color: 'var(--tg-color-text-secondary)', display: 'block', marginTop: 4 }}>
                        {paymentErrors.stripe_cancel_url}
                      </small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Lite (USD)</label>
                    <input
                      className="form-input"
                      type="number"
                      step="0.01"
                      value={form.payments.stripe.priceUsdLite}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, priceUsdLite: Number(e.target.value) } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Pro (USD)</label>
                    <input
                      className="form-input"
                      type="number"
                      step="0.01"
                      value={form.payments.stripe.priceUsdPro}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: { ...p.payments, stripe: { ...p.payments.stripe, priceUsdPro: Number(e.target.value) } },
                        }))
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Price Ent (USD)</label>
                    <input
                      className="form-input"
                      type="number"
                      step="0.01"
                      value={form.payments.stripe.priceUsdEnterprise}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, priceUsdEnterprise: Number(e.target.value) },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SuperAdmin;
