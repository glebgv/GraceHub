export function formatDurationSeconds(totalSeconds: number, locale = 'ru'): string {
  const s = Math.max(0, Math.floor(totalSeconds || 0));

  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;

  // Intl.DurationFormat (если поддерживается браузером)
  const DF = (Intl as any)?.DurationFormat;
  if (typeof DF === 'function') {
    return new DF(locale, { style: 'short' }).format({ days, hours, minutes, seconds });
  }

  // Fallback (если Intl.DurationFormat недоступен)
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  parts.push(`${seconds}s`);
  return parts.join(' ');
}

