export function formatDurationMs(durationMs: number): string {
  if (!Number.isFinite(durationMs) || durationMs < 0) {
    return '—'
  }

  const totalSeconds = Math.floor(durationMs / 1000)
  if (totalSeconds < 60) {
    return `${totalSeconds}s`
  }

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes < 60) {
    return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes === 0 ? `${hours}h` : `${hours}h ${String(remainingMinutes).padStart(2, '0')}m`
}

export function formatBacktestWallRuntime(
  item: {
    status: string
    created_at: string
    updated_at: string
    started_at?: string | null
    finished_at?: string | null
  },
  nowMs: number = Date.now(),
): string {
  if (item.status === 'pending') {
    return '—'
  }

  const startMs = Date.parse(item.started_at ?? item.created_at)
  if (Number.isNaN(startMs)) {
    return '—'
  }

  if (item.status === 'running') {
    return formatDurationMs(nowMs - startMs)
  }

  const finishMs = item.finished_at
    ? Date.parse(item.finished_at)
    : Date.parse(item.updated_at)
  if (Number.isNaN(finishMs)) {
    return '—'
  }

  return formatDurationMs(finishMs - startMs)
}
