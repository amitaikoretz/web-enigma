import type { BusinessDay, Time, UTCTimestamp } from 'lightweight-charts'
import { TickMarkType } from 'lightweight-charts'

import type { TimeDisplayFormat } from '../types/settings'

export function toChartTime(timestamp: string, resolution: string): Time {
  if (resolution === '1d') {
    return timestamp.slice(0, 10) as Time
  }
  return Math.floor(Date.parse(timestamp) / 1000) as UTCTimestamp
}

function isBusinessDay(time: Time): time is BusinessDay {
  return typeof time === 'object' && time !== null && 'year' in time
}

export function chartTimeToMs(time: Time): number {
  if (typeof time === 'number') {
    return time * 1000
  }
  if (isBusinessDay(time)) {
    return Date.UTC(time.year, time.month - 1, time.day)
  }
  return Date.parse(`${time}T00:00:00Z`)
}

function formatDailyChartDate(time: Time): string {
  if (typeof time === 'string') {
    return time
  }
  if (isBusinessDay(time)) {
    const month = String(time.month).padStart(2, '0')
    const day = String(time.day).padStart(2, '0')
    return `${time.year}-${month}-${day}`
  }
  return String(time)
}

export function formatChartTime(
  time: Time,
  timezone: string,
  timeDisplayFormat: TimeDisplayFormat,
): string {
  if (typeof time !== 'number') {
    return formatDailyChartDate(time)
  }

  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: timeDisplayFormat === '12h',
  }).format(new Date(time * 1000))
}

export function createChartTimeFormatter(
  timezone: string,
  timeDisplayFormat: TimeDisplayFormat,
): (time: Time) => string {
  return (time) => formatChartTime(time, timezone, timeDisplayFormat)
}

export function createChartTickMarkFormatter(
  timezone: string,
  timeDisplayFormat: TimeDisplayFormat,
): (time: Time, tickMarkType: TickMarkType) => string | null {
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  const timeFormatter = new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: timeDisplayFormat === '12h',
  })
  const monthFormatter = new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    month: 'short',
    year: 'numeric',
  })
  const yearFormatter = new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    year: 'numeric',
  })

  return (time, tickMarkType) => {
    if (typeof time !== 'number') {
      return formatDailyChartDate(time)
    }

    const date = new Date(time * 1000)
    if (tickMarkType === TickMarkType.Year) {
      return yearFormatter.format(date)
    }
    if (tickMarkType === TickMarkType.Month) {
      return monthFormatter.format(date)
    }
    if (tickMarkType === TickMarkType.Time || tickMarkType === TickMarkType.TimeWithSeconds) {
      return timeFormatter.format(date)
    }
    return dateFormatter.format(date)
  }
}
