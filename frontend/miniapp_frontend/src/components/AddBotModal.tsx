// src/components/AddBotModal.tsx

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';

interface AddBotModalProps {
  onClose: () => void;
  onSubmitToken: (token: string) => Promise<void> | void;
}

const AddBotModal: React.FC<AddBotModalProps> = ({ onClose, onSubmitToken }) => {
  const { t } = useTranslation();
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim() || loading) return;
    try {
      setLoading(true);
      await onSubmitToken(token.trim());
      onClose();
    } catch (err) {
      console.error('[AddBotModal] Submit error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer.Root 
      open={true} 
      onOpenChange={(open) => !open && !loading && onClose()}
      modal={true}
    >
      <Drawer.Portal>
        <Drawer.Overlay
          className="fixed inset-0 bg-black/40"
          style={{ zIndex: 9998 }}
        />
        <Drawer.Content
          style={{
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            zIndex: 9999,
            background: 'var(--tg-theme-bg-color, #ffffff)',
            color: 'var(--tg-theme-text-color, #000000)',
            borderTopLeftRadius: 20,
            borderTopRightRadius: 20,
            outline: 'none',
          }}
        >
          <div style={{ padding: '12px 16px 24px' }}>
            {/* Drag handle */}
            <div
              style={{
                width: 40,
                height: 4,
                borderRadius: 999,
                background: 'var(--tg-theme-hint-color, rgba(0,0,0,0.3))',
                margin: '0 auto 12px',
              }}
            />

            {/* Header */}
            <h3
              style={{
                margin: '0 0 6px 0',
                fontSize: 18,
                fontWeight: 600,
                color: 'var(--tg-theme-text-color)',
              }}
            >
              🤖 {t('firstLaunch.addBot')}
            </h3>

            {/* Description */}
            <p
              style={{
                margin: '0 0 16px 0',
                fontSize: 13,
                color: 'var(--tg-theme-hint-color)',
                lineHeight: 1.4,
              }}
            >
              {t('firstLaunch.addBotHint')}
            </p>

            {/* Form */}
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label
                  style={{
                    display: 'block',
                    marginBottom: 6,
                    fontSize: 13,
                    fontWeight: 500,
                    color: 'var(--tg-theme-text-color)',
                  }}
                >
                  {t('firstLaunch.botTokenLabel')}
                </label>
                <input
                  type="text"
                  placeholder={t('firstLaunch.botTokenPlaceholder') || '123456:ABC-DEF...'}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  disabled={loading}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 10,
                    border: '1px solid rgba(148, 163, 184, 0.5)',
                    background: 'rgba(0, 0, 0, 0.04)',
                    color: 'var(--tg-theme-text-color)',
                    fontSize: 14,
                    fontFamily: 'monospace',
                  }}
                />
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--outline"
                  onClick={onClose}
                  disabled={loading}
                  style={{ flex: 1 }}
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={loading || !token.trim()}
                  style={{ flex: 1 }}
                >
                  {loading ? t('common.saving') : t('firstLaunch.connectBot')}
                </button>
              </div>
            </form>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
};

export default AddBotModal;
