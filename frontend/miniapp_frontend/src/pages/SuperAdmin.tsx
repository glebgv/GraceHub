// src/pages/SuperAdmin.tsx
//
// NEW (FirstLaunch offer gating):
// - Добавлен блок настроек "Offer (FirstLaunch)" -> miniapp_public.offer.enabled + miniapp_public.offer.url
// - URL валидируется как https://
// - В save() проходит через нормализацию mergeDefaults/normalizeIds, как и остальная форма
// - Модальные окна переработаны на Vaul Drawer
// - Premium sticky Save button через Vaul Drawer
// - Полностью переработано на Telegram-идентичность с классами из App.css

import React, { useEffect, useMemo, useState } from 'react';
import { Drawer } from 'vaul';

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
      successUrl: '',
      cancelUrl: '',
      priceUsdLite: 4.99,
      priceUsdPro: 9.99,
      priceUsdEnterprise: 29.99,
    },
  },
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
    className="icon-trash"
  >
    <path
      d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v10h-2V9Zm4 0h2v10h-2V9ZM6 7h12l-1 14H7L6 7Z"
      fill="currentColor"
    />
  </svg>
);

type BaseDrawerProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
};

const BaseDrawer: React.FC<BaseDrawerProps> = ({ open, title, onClose, children }) => {
  return (
    <Drawer.Root open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Drawer.Portal>
        <Drawer.Overlay className="drawer-overlay" />
        <Drawer.Content className="drawer-content superadmin-drawer">
          <div className="drawer-handle" />
          <div className="drawer-body">
            <div className="drawer-header">
              <Drawer.Title className="drawer-title">{title}</Drawer.Title>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={onClose}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            {children}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
};

type InfoDrawerProps = {
  open: boolean;
  title: string;
  text?: string;
  onClose: () => void;
};

const InfoDrawer: React.FC<InfoDrawerProps> = ({ open, title, text, onClose }) => {
  return (
    <BaseDrawer open={open} title={title} onClose={onClose}>
      {text ? <div className="drawer-text">{text}</div> : null}
      <div className="drawer-footer drawer-footer-end">
        <button type="button" className="btn btn--primary" onClick={onClose}>
          OK
        </button>
      </div>
    </BaseDrawer>
  );
};

type ConfirmExitDrawerProps = {
  open: boolean;
  onExit: () => void;
  onStay: () => void;
};

const ConfirmExitDrawer: React.FC<ConfirmExitDrawerProps> = ({ open, onExit, onStay }) => {
  return (
    <BaseDrawer open={open} title="Подтверждение" onClose={onStay}>
      <div className="drawer-text">У вас несохраненные изменения. Выйти?</div>
      <div className="drawer-footer">
        <button type="button" className="btn btn--secondary" onClick={onStay}>
          Назад
        </button>
        <button type="button" className="btn btn--primary" onClick={onExit}>
          Выход
        </button>
      </div>
    </BaseDrawer>
  );
};

type ConfirmDeleteDrawerProps = {
  open: boolean;
  title?: string;
  text?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

const ConfirmDeleteDrawer: React.FC<ConfirmDeleteDrawerProps> = ({
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
    <BaseDrawer open={open} title={title} onClose={onCancel}>
      <div className="drawer-text">{text}</div>
      <div className="drawer-footer">
        <button type="button" className="btn btn--secondary" onClick={onCancel}>
          {cancelText}
        </button>
        <button
          type="button"
          className={danger ? 'btn btn--danger' : 'btn btn--primary'}
          onClick={onConfirm}
        >
          {confirmText}
        </button>
      </div>
    </BaseDrawer>
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

const MiniSwitch: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  ariaLabel: string;
}> = ({ checked, onChange, disabled, ariaLabel }) => {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-pressed={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`mini-switch ${checked ? 'mini-switch--on' : 'mini-switch--off'} ${disabled ? 'mini-switch--disabled' : ''}`}
    >
      <span aria-hidden="true" className="mini-switch-knob" />
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

  const [savedDrawerOpen, setSavedDrawerOpen] = useState(false);
  const [confirmExitOpen, setConfirmExitOpen] = useState(false);

  const [addSuperadminOpen, setAddSuperadminOpen] = useState(false);
  const [addSuperadminValue, setAddSuperadminValue] = useState('');

  const [paymentErrors, setPaymentErrors] = useState<Record<string, string>>({});
  const [offerErrors, setOfferErrors] = useState<Record<string, string>>({});

  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<
    null | { kind: 'superadmin'; id: number } | { kind: 'owner'; id: number }
  >(null);

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
        const [meData, settings] = await Promise.all([
          apiClient.getMe(),
          apiClient.getMiniappPublicSettings(),
        ]);
        if (cancelled) return;

        const merged = mergeDefaults(settings);

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

    if (v.payments.enabled.stripe) {
      const s = (v.payments.stripe.successUrl || '').trim();
      const c = (v.payments.stripe.cancelUrl || '').trim();

      if (!s) errs.stripe_success_url = 'Stripe successUrl обязателен.';
      else if (!isHttpsUrl(s))
        errs.stripe_success_url = 'Stripe successUrl должен начинаться с https://';

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
      setSavedDrawerOpen(true);
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
        allowedUserIds: Array.from(
          new Set([...(prev.singleTenant.allowedUserIds || []), id]),
        ).sort((a, b) => a - b),
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

  if (loading)
    return (
      <div className="superadmin-page">
        <div className="card">
          <div className="loading-spinner" />
          <p className="text-center">Loading superadmin…</p>
        </div>
      </div>
    );

  if (!isSuperadmin) {
    return (
      <div className="superadmin-page">
        <div className="card error-card">
          <p className="error-text">Forbidden: superadmin only</p>
        </div>
      </div>
    );
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
    <div className="superadmin-page">
      {/* Header */}
      <div className="card superadmin-header">
        <div className="superadmin-header-content">
          <img src={logoRed} alt="GraceHub" className="superadmin-logo" />
          <span className="superadmin-title">GraceHub Admin Panel</span>
        </div>
      </div>

      <InfoDrawer
        open={savedDrawerOpen}
        title={t('superAdmin.saved_title')}
        text={t('superAdmin.saved_text')}
        onClose={() => setSavedDrawerOpen(false)}
      />

      <ConfirmExitDrawer
        open={confirmExitOpen}
        onStay={() => setConfirmExitOpen(false)}
        onExit={() => {
          setConfirmExitOpen(false);
          onBack?.();
        }}
      />

      <ConfirmDeleteDrawer
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

      <BaseDrawer
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

        <div className="drawer-footer">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => setAddOwnerOpen(false)}
          >
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={submitAddOwner}>
            Add
          </button>
        </div>
      </BaseDrawer>

      <BaseDrawer
        open={addSuperadminOpen}
        title={t('superAdmin.add_superadmin_title')}
        onClose={() => setAddSuperadminOpen(false)}
      >
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
        <div className="drawer-footer">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => setAddSuperadminOpen(false)}
          >
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={submitAddSuperadmin}>
            Add
          </button>
        </div>
      </BaseDrawer>

      <div className="card superadmin-main">
        <div className="card-header">
          <div className="card-title">Superadmin panel</div>
          <div className="superadmin-actions">
            {onBack && (
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handleBack}
                disabled={saving}
              >
                ← Back
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="card error-card superadmin-error">
            <p className="error-text">{error}</p>
          </div>
        )}

        {/* Offer (FirstLaunch) */}
        <div className="card superadmin-section">
          <h3 className="superadmin-section-title">Offer (FirstLaunch)</h3>

          <div className="form-group form-group-row">
            <label className="form-label">Require offer acceptance</label>
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
            <div className="superadmin-subsection">
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
                      offer_url: !v
                        ? 'URL оферты обязателен.'
                        : isHttpsUrl(v)
                          ? ''
                          : 'URL оферты должен начинаться с https://',
                    }));
                  }}
                />
                {offerErrors.offer_url ? (
                  <small className="form-error">{offerErrors.offer_url}</small>
                ) : null}
              </div>

              <div className="form-hint">{t('superAdmin.firstLaunch_offer_block_hint')}</div>
            </div>
          )}
        </div>

        {/* Single-tenant */}
        <div className="card superadmin-section">
          <h3 className="superadmin-section-title">Single-tenant</h3>

          <div className="form-group form-group-row">
            <label className="form-label">Enable single-tenant mode</label>
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
              <div className="form-group">
                <label className="form-label">Owner Telegram IDs</label>
                <button
                  className="btn btn--secondary"
                  type="button"
                  onClick={openAddOwner}
                  disabled={saving}
                >
                  Add
                </button>

                <div className="superadmin-list">
                  {(form.singleTenant.allowedUserIds || []).length === 0 ? (
                    <div className="superadmin-list-empty">No IDs configured.</div>
                  ) : (
                    (form.singleTenant.allowedUserIds || []).map((id) => (
                      <div key={id} className="superadmin-list-item">
                        <div className="superadmin-list-item-text">{id}</div>
                        <button
                          type="button"
                          className="btn btn--outline btn--sm"
                          onClick={() => requestDeleteOwner(id)}
                          title={`Удалить ${id}`}
                          aria-label={`Удалить ${id}`}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                <div className="form-hint">{t('superAdmin.single_tenant_allowlist_hint')}</div>
              </div>
            </>
          )}
        </div>

        {/* Superadmins */}
        <div className="card superadmin-section">
          <h3 className="superadmin-section-title">Superadmins</h3>

          <button
            className="btn btn--secondary"
            onClick={openAddSuperadmin}
            type="button"
            disabled={saving}
          >
            Add superadmin
          </button>

          <div className="superadmin-list">
            {(form.superadmins || []).length === 0 ? (
              <div className="superadmin-list-empty">
                No superadmins configured in DB settings.
              </div>
            ) : (
              (form.superadmins || []).map((id) => (
                <div key={id} className="superadmin-list-item">
                  <div className="superadmin-list-item-text">{id}</div>
                  <button
                    type="button"
                    className="btn btn--outline btn--sm"
                    onClick={() => requestDeleteSuperadmin(id)}
                    title={`Удалить ${id}`}
                    aria-label={`Удалить ${id}`}
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Instance defaults */}
        <div className="card superadmin-section">
          <h3 className="superadmin-section-title">Instance defaults</h3>

          <div className="form-group">
            <label className="form-label">{t('superAdmin.antiflood_limit_hint')}</label>
            <input
              className="form-input"
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
                  instanceDefaults: {
                    ...p.instanceDefaults,
                    maxInstancesPerUser: Number(e.target.value),
                  },
                }))
              }
            />
          </div>
        </div>

        {/* Payments */}
        <div className="card superadmin-section">
          <h3 className="superadmin-section-title">Payments (UI)</h3>

          {form.singleTenant.enabled ? (
            <div className="info-banner">
              {t('superAdmin.single_tenant_payments_disabled_hint')}
            </div>
          ) : (
            <>
              {/* Telegram Stars */}
              <div className="form-group form-group-row">
                <label className="form-label">Telegram Stars</label>
                <MiniSwitch
                  checked={form.payments.enabled.telegramStars}
                  disabled={saving}
                  ariaLabel="Toggle Telegram Stars"
                  onChange={(checked) =>
                    setForm((p) => ({
                      ...p,
                      payments: {
                        ...p.payments,
                        enabled: { ...p.payments.enabled, telegramStars: checked },
                      },
                    }))
                  }
                />
              </div>

              {form.payments.enabled.telegramStars && (
                <div className="superadmin-subsection">
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
                            telegramStars: {
                              ...p.payments.telegramStars,
                              priceStarsLite: Number(e.target.value),
                            },
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
                            telegramStars: {
                              ...p.payments.telegramStars,
                              priceStarsPro: Number(e.target.value),
                            },
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
              <div className="form-group form-group-row">
                <label className="form-label">TON</label>
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
                <div className="superadmin-subsection">
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
                          ton_wallet: isTonFriendlyAddressLike(v)
                            ? ''
                            : 'Некорректный TON-адрес (friendly).',
                        }));
                      }}
                    />
                    {paymentErrors.ton_wallet ? (
                      <small className="form-error">{paymentErrors.ton_wallet}</small>
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
                      <small className="form-error">{paymentErrors.ton_api}</small>
                    ) : null}
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      API key <small className="form-label-optional">(необязательно)</small>
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
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, checkDelaySeconds: n },
                          },
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
                      <small className="form-error">{paymentErrors.ton_delay}</small>
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
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, confirmationsRequired: n },
                          },
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
                      <small className="form-error">{paymentErrors.ton_confirmations}</small>
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
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, pricePerPeriodLite: Number(e.target.value) },
                          },
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
                          payments: {
                            ...p.payments,
                            ton: { ...p.payments.ton, pricePerPeriodPro: Number(e.target.value) },
                          },
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
              <div className="form-group form-group-row">
                <label className="form-label">YooKassa</label>
                <MiniSwitch
                  checked={form.payments.enabled.yookassa}
                  disabled={saving}
                  ariaLabel="Toggle YooKassa payments"
                  onChange={(checked) =>
                    setForm((p) => ({
                      ...p,
                      payments: {
                        ...p.payments,
                        enabled: { ...p.payments.enabled, yookassa: checked },
                      },
                    }))
                  }
                />
              </div>

              {form.payments.enabled.yookassa && (
                <div className="superadmin-subsection">
                  <div className="form-group">
                    <label className="form-label">Shop ID</label>
                    <input
                      className="form-input"
                      value={form.payments.yookassa.shopId}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, shopId: e.target.value },
                          },
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
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, secretKey: e.target.value },
                          },
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
                          payments: {
                            ...p.payments,
                            yookassa: { ...p.payments.yookassa, returnUrl: v },
                          },
                        }));
                        setPaymentErrors((prev) => ({ ...prev, yk_return: '' }));
                      }}
                      onBlur={() => {
                        const v = (form.payments.yookassa.returnUrl || '').trim();
                        setPaymentErrors((prev) => ({
                          ...prev,
                          yk_return: isHttpsUrl(v)
                            ? ''
                            : 'Return URL должен начинаться с https://',
                        }));
                      }}
                    />
                    {paymentErrors.yk_return ? (
                      <small className="form-error">{paymentErrors.yk_return}</small>
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
                            yookassa: {
                              ...p.payments.yookassa,
                              priceRubLite: Number(e.target.value),
                            },
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
                            yookassa: {
                              ...p.payments.yookassa,
                              priceRubEnterprise: Number(e.target.value),
                            },
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              )}

              {/* Stripe */}
              <div className="form-group form-group-row">
                <label className="form-label">Stripe</label>
                <MiniSwitch
                  checked={form.payments.enabled.stripe}
                  disabled={saving}
                  ariaLabel="Toggle Stripe payments"
                  onChange={(checked) => {
                    setForm((p) => ({
                      ...p,
                      payments: {
                        ...p.payments,
                        enabled: { ...p.payments.enabled, stripe: checked },
                      },
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
                <div className="superadmin-subsection">
                  <div className="form-group">
                    <label className="form-label">Secret Key</label>
                    <input
                      className="form-input"
                      value={form.payments.stripe.secretKey}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, secretKey: e.target.value },
                          },
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
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, webhookSecret: e.target.value },
                          },
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
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, successUrl: v },
                          },
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
                      <small className="form-error">{paymentErrors.stripe_success_url}</small>
                    ) : null}
                  </div>

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
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, cancelUrl: v },
                          },
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
                      <small className="form-error">{paymentErrors.stripe_cancel_url}</small>
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
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, priceUsdLite: Number(e.target.value) },
                          },
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
                          payments: {
                            ...p.payments,
                            stripe: { ...p.payments.stripe, priceUsdPro: Number(e.target.value) },
                          },
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
                            stripe: {
                              ...p.payments.stripe,
                              priceUsdEnterprise: Number(e.target.value),
                            },
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

      {/* Premium Sticky Save Button */}
      {dirty && (
        <Drawer.Root open={true} modal={false} dismissible={false}>
          <Drawer.Portal>
            <Drawer.Content className="sticky-save-button">
              <div className="sticky-save-inner">
                <div className="sticky-save-container">
                  <div className="sticky-save-indicator">
                    <div className="sticky-save-pulse" />
                    <span>Несохраненные изменения</span>
                  </div>

                  <button
                    type="button"
                    onClick={save}
                    disabled={saving}
                    className={`btn btn--primary btn--save ${saving ? 'btn--saving' : ''}`}
                  >
                    {saving ? (
                      <>
                        <svg className="save-spinner" width="20" height="20" viewBox="0 0 24 24">
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeDasharray="32 32"
                            opacity="0.3"
                          />
                          <path
                            d="M12 2a10 10 0 0 1 10 10"
                            stroke="currentColor"
                            strokeWidth="3"
                            strokeLinecap="round"
                          />
                        </svg>
                        <span>Сохранение...</span>
                      </>
                    ) : (
                      <>
                        <svg className="save-icon" width="20" height="20" viewBox="0 0 24 24">
                          <path
                            d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            fill="none"
                          />
                          <path
                            d="M17 21v-8H7v8M7 3v5h8"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                        <span>Сохранить настройки</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      )}
    </div>
  );
};

export default SuperAdmin;
