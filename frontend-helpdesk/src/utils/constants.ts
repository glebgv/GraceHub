export const TICKET_STATUS_LABELS: Record<string, string> = {
  new: 'Новый',
  inprogress: 'В работе',
  answered: 'Отвеченный',
  closed: 'Закрыт',
  spam: 'Спам'
};

export const TICKET_STATUS_EMOJI: Record<string, string> = {
  new: '🆕',
  inprogress: '⏳',
  answered: '✅',
  closed: '🔒',
  spam: '🚫'
};

export const TICKET_STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  inprogress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  answered: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  closed: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
  spam: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
};

export const OPERATOR_ROLE_LABELS: Record<string, string> = {
  owner: 'Владелец',
  operator: 'Оператор',
  viewer: 'Просмотр'
};

export const API_TIMEOUT = 30000; // 30 seconds
export const POLL_INTERVAL = 5000; // 5 seconds

