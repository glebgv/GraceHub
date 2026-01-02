import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'  // <-- ИСПРАВЛЕНО: был ../apiclient

interface TicketActionParams {
  instanceId: string
  chatId: number
  threadId: number
  ticketId: number
  operatorId: number
}

const TicketActions: React.FC = () => {
  const { t } = useTranslation()
  const [params, setParams] = useState<TicketActionParams | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    const tg = (window as any).Telegram?.WebApp
    const initData = tg?.initData

    if (!initData) {
      setError('Должно быть открыто из Telegram')
      return
    }

    // Парсим GET-параметры из URL
    const urlParams = new URLSearchParams(window.location.search)
    const instanceId = urlParams.get('instanceId')
    const chatId = Number(urlParams.get('chatId'))
    const threadId = Number(urlParams.get('threadId'))
    const ticketId = Number(urlParams.get('ticketId'))
    const operatorId = Number(urlParams.get('operatorId'))

    if (!instanceId || !chatId || !threadId || !ticketId) {
      setError('Неверные параметры URL')
      return
    }

    setParams({ instanceId, chatId, threadId, ticketId, operatorId })

    // Аутентификация
    apiClient.setInitData(initData)
    apiClient.authTelegram({ initData }).then(auth => {
      apiClient.setToken(auth.token)
    }).catch(err => {
      setError('Ошибка авторизации: ' + err.message)
    })

    // Настраиваем Telegram WebApp
    tg?.ready()
    tg?.expand()
  }, [])

  const handleAction = async (action: 'self' | 'spam' | 'close') => {
    if (!params) return
    
    setLoading(true)
    setError(null)
    setSuccess(null)
    
    try {
      let status: string
      let actionText: string

      switch (action) {
        case 'self':
          status = 'inprogress'
          actionText = 'Тикет взят в работу'
          // TODO: Добавь API endpoint для assign, если нужно
          break
        case 'spam':
          status = 'spam'
          actionText = 'Тикет отмечен как спам'
          break
        case 'close':
          status = 'closed'
          actionText = 'Тикет закрыт'
          break
      }
      
      await apiClient.updateTicketStatus(params.instanceId, params.ticketId, { status })
      
      setSuccess(actionText)
      
      // Закрываем Mini App через 1 секунду
      setTimeout(() => {
        ;(window as any).Telegram?.WebApp?.close()
      }, 1000)
    } catch (err: any) {
      setError(err?.message || 'Ошибка при выполнении действия')
    } finally {
      setLoading(false)
    }
  }

  if (error) {
    return (
      <div style={{ 
        padding: 16, 
        color: 'var(--tg-theme-destructive-text-color, #dc2626)',
        textAlign: 'center'
      }}>
        ❌ {error}
      </div>
    )
  }

  if (!params) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        Загрузка...
      </div>
    )
  }

  if (success) {
    return (
      <div style={{ 
        padding: 16, 
        color: 'var(--tg-theme-link-color, #16a34a)',
        textAlign: 'center',
        fontSize: 16
      }}>
        ✅ {success}
      </div>
    )
  }

  return (
    <div style={{ 
      padding: 16,
      background: 'var(--tg-theme-bg-color, #fff)',
      minHeight: '100vh'
    }}>
      <h3 style={{ 
        marginTop: 0, 
        marginBottom: 16,
        color: 'var(--tg-theme-text-color, #000)'
      }}>
        Тикет #{params.ticketId}
      </h3>
      
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: 12 
      }}>
        <button
          onClick={() => handleAction('self')}
          disabled={loading}
          style={{ 
            padding: 14,
            fontSize: 16,
            borderRadius: 8,
            border: 'none',
            background: 'var(--tg-theme-button-color, #3390ec)',
            color: 'var(--tg-theme-button-text-color, #fff)',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1
          }}
        >
          👤 Взять себе
        </button>
        
        <button
          onClick={() => handleAction('spam')}
          disabled={loading}
          style={{ 
            padding: 14,
            fontSize: 16,
            borderRadius: 8,
            border: 'none',
            background: '#dc2626',
            color: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1
          }}
        >
          🚫 Спам
        </button>
        
        <button
          onClick={() => handleAction('close')}
          disabled={loading}
          style={{ 
            padding: 14,
            fontSize: 16,
            borderRadius: 8,
            border: 'none',
            background: '#16a34a',
            color: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1
          }}
        >
          ✅ Закрыть
        </button>
      </div>
    </div>
  )
}

export default TicketActions
