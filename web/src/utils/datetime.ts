import dayjs from 'dayjs'

import type { TimeDisplayFormat } from '../types/settings'

export function formatInTimezone(
  value: string,
  timezone: string,
  timeDisplayFormat: TimeDisplayFormat,
  includeSeconds = false,
): string {
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) {
    return dayjs(value).format(includeSeconds ? 'MMM D, YYYY HH:mm:ss' : 'MMM D, YYYY HH:mm')
  }

  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
    hour12: timeDisplayFormat === '12h',
  }).format(date)
}
