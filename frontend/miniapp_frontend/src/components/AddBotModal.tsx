import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

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
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">🤖 {t('firstLaunch.addBot')}</h2>
          <button
            className="modal-close"
            onClick={onClose}
            type="button"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="modal-body">
          <p style={{ margin: 0 }}>{t('firstLaunch.addBotHint')}</p>

          <form onSubmit={handleSubmit}>
            <div className="modal-field">
              <label className="modal-label">
                {t('firstLaunch.botTokenLabel')}
              </label>
              <input
                className="modal-input"
                placeholder={
                  t('firstLaunch.botTokenPlaceholder') || '123456:ABC-DEF...'
                }
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--outline"
                onClick={onClose}
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || !token.trim()}
              >
                {loading ? t('common.saving') : t('firstLaunch.connectBot')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AddBotModal;

