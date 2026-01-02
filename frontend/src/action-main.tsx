import React from 'react'
import ReactDOM from 'react-dom/client'
import TicketActions from './pages/TicketActions'
import './i18n'

ReactDOM.createRoot(document.getElementById('action-root')!).render(
  <React.StrictMode>
    <TicketActions />
  </React.StrictMode>
)

