import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchApiHealth } from '../api/health'
import type { ApiHealthSnapshot, ApiHealthStatus } from '../types/health'

const HEALTH_POLL_INTERVAL_MS = 5000

export function useApiHealth(pollIntervalMs = HEALTH_POLL_INTERVAL_MS): ApiHealthSnapshot {
  const [status, setStatus] = useState<ApiHealthStatus>('checking')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inFlightRef = useRef(false)

  const checkHealth = useCallback(async () => {
    if (inFlightRef.current) {
      return
    }

    inFlightRef.current = true
    const controller = new AbortController()
    const startedAt = performance.now()

    try {
      await fetchApiHealth(controller.signal)
      setStatus('connected')
      setLatencyMs(Math.round(performance.now() - startedAt))
      setLastCheckedAt(new Date().toISOString())
      setError(null)
    } catch (err) {
      if (controller.signal.aborted) {
        return
      }
      setStatus('disconnected')
      setLatencyMs(null)
      setLastCheckedAt(new Date().toISOString())
      setError(err instanceof Error ? err.message : 'Health check failed')
    } finally {
      inFlightRef.current = false
    }
  }, [])

  useEffect(() => {
    void checkHealth()

    const poll = () => {
      if (document.visibilityState !== 'visible') {
        return
      }
      void checkHealth()
    }

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        void checkHealth()
      }
    }

    const handleOnline = () => {
      void checkHealth()
    }

    const timer = window.setInterval(poll, pollIntervalMs)
    document.addEventListener('visibilitychange', handleVisibility)
    window.addEventListener('online', handleOnline)

    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibility)
      window.removeEventListener('online', handleOnline)
    }
  }, [checkHealth, pollIntervalMs])

  return { status, latencyMs, lastCheckedAt, error }
}
