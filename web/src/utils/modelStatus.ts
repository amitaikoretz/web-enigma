import type { ModelStatus } from '../types/modelFamilies'

export function statusChipColor(status: ModelStatus): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  if (status === 'pending') return 'warning'
  return 'default'
}

export function isModelActive(status: ModelStatus): boolean {
  return status === 'pending' || status === 'running'
}

export function statusFromArgoPhase(phase: string | null | undefined): ModelStatus | null {
  if (!phase) {
    return null
  }

  const normalized = phase.trim().toLowerCase()
  if (normalized === 'succeeded') return 'succeeded'
  if (normalized === 'failed' || normalized === 'error') return 'failed'
  if (normalized === 'pending' || normalized === 'queued') return 'pending'
  if (normalized === 'running') return 'running'
  if (normalized === 'canceled' || normalized === 'killed') return 'canceled'
  return null
}

export function resolveModelStatus(
  currentStatus: ModelStatus,
  argoPhase: string | null | undefined,
): ModelStatus {
  if (!isModelActive(currentStatus)) {
    return currentStatus
  }

  return statusFromArgoPhase(argoPhase) ?? currentStatus
}
