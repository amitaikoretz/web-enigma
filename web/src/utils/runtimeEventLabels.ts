const EVENT_TYPE_LABELS: Record<string, string> = {
  controller_sync: 'Controller sync',
  worker_started: 'Worker started',
  assignments_refreshed: 'Assignments refreshed',
  lease_acquired: 'Lease acquired',
  lease_skipped: 'Lease skipped',
  worker_iteration: 'Worker iteration',
  worker_draining: 'Worker draining',
  reconciliation_symbol: 'Reconciliation (symbol)',
  reconciliation_worker: 'Reconciliation (worker)',
  reconciliation_run: 'Reconciliation run',
}

export const STALE_HEARTBEAT_THRESHOLD_MS = 15_000

export function formatEventType(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] ?? eventType.replaceAll('_', ' ')
}

export function isStaleHeartbeat(updatedAt: string, now = Date.now()): boolean {
  const timestamp = new Date(updatedAt).valueOf()
  if (Number.isNaN(timestamp)) {
    return false
  }
  return now - timestamp > STALE_HEARTBEAT_THRESHOLD_MS
}

export const KNOWN_EVENT_TYPES = Object.keys(EVENT_TYPE_LABELS)
