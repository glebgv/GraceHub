// src/components/AddBotModal.tsx

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'vaul';

interface AddBotModalProps {
  open: boolean;
  onClose: () => void;
  onSubmitToken: (token: string) => Promise<void> | void;
  validateToken?: (token: string) => boolean;
  getErrorMessage?: () => string;
}

const AddBotModal: React.FC<AddBotModalProps> = ({ 
  open,
  onClose, 
  onSubmitToken,
  validateToken,
  getErrorMessage,
}) => {
  const { t } = useTranslation();
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Сброс состояния при открытии/закрытии модалки
  useEffect(() => {
    if (open) {
      setToken('');
      setError(null);
      setLoading(false);
    }
  }, [open]);

  const handleTokenChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setToken(value);
    
    // Validate only if token is not empty and validator is provided
    if (value.trim() && validateToken) {
      if (!validateToken(value.trim())) {
        setError(getErrorMessage?.() || 'Invalid token format');
      } else {
        setError(null);
      }
    } else {
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim() || loading || error) return;
    
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

  const handleClose = () => {
    if (!loading) {
      onClose();
    }
  };

  const isSubmitDisabled = !token.trim() || !!error || loading;

  return (
    <Drawer.Root 
      open={open} 
      onOpenChange={(isOpen) => {
        if (!isOpen && !loading) {
          onClose();
        }
      }}
      modal={true}
    >
      <Drawer.Portal>
        <Drawer.Overlay
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            zIndex: 9998,
          }}
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
          aria-describedby="add-bot-description"
        >
          <Drawer.Title
            style={{
              margin: '12px 16px 6px',
              fontSize: 18,
              fontWeight: 600,
              color: 'var(--tg-theme-text-color)',
            }}
          >
            🤖 {t('firstLaunch.addBot')}
          </Drawer.Title>

          <div style={{ padding: '0 16px 24px' }}>
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

            {/* Description */}
            <p
              id="add-bot-description"
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
                  htmlFor="bot-token-input"
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
                  id="bot-token-input"
                  type="text"
                  placeholder={t('firstLaunch.botTokenPlaceholder') || '123456:ABC-DEF...'}
                  value={token}
                  onChange={handleTokenChange}
                  disabled={loading}
                  autoFocus
                  aria-invalid={!!error}
                  aria-describedby={error ? 'token-error' : undefined}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 10,
                    border: error 
                      ? '1px solid rgba(239, 68, 68, 0.8)' 
                      : '1px solid rgba(148, 163, 184, 0.5)',
                    background: 'rgba(0, 0, 0, 0.04)',
                    color: 'var(--tg-theme-text-color)',
                    fontSize: 14,
                    fontFamily: 'monospace',
                  }}
                />
                
                {/* Validation error message */}
                {error && (
                  <div
                    id="token-error"
                    role="alert"
                    style={{
                      marginTop: 6,
                      fontSize: 12,
                      color: 'rgb(239, 68, 68)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <span aria-hidden="true">⚠️</span>
                    <span>{error}</span>
                  </div>
                )}
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--outline"
                  onClick={handleClose}
                  disabled={loading}
                  style={{ flex: 1 }}
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={isSubmitDisabled}
                  style={{ 
                    flex: 1,
                    opacity: isSubmitDisabled ? 0.5 : 1,
                    cursor: isSubmitDisabled ? 'not-allowed' : 'pointer',
                  }}
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
