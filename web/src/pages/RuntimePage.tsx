import RefreshIcon from '@mui/icons-material/Refresh'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fetchLiveRuntime, type LiveRuntimeFilters } from '../api/liveRuntime'
import { RuntimeEventsTable } from '../components/RuntimeEventsTable'
import { RuntimeStatePanel } from '../components/RuntimeStatePanel'
import { useSettings } from '../settings/useSettings'
import type { LiveRuntimeResponse } from '../types/liveRuntime'
import { formatInTimezone } from '../utils/datetime'

const DEFAULT_LIMIT = 100

function parseLimit(value: string | null): number {
  const parsed = Number(value)
  if (parsed === 50 || parsed === 100 || parsed === 200) {
    return parsed
  }
  return DEFAULT_LIMIT
}

function filtersFromSearchParams(searchParams: URLSearchParams): LiveRuntimeFilters {
  return {
    limit: parseLimit(searchParams.get('limit')),
    worker_id: searchParams.get('worker_id') ?? undefined,
    event_type: searchParams.get('event_type') ?? undefined,
    symbol_key: searchParams.get('symbol_key') ?? undefined,
  }
}

function searchParamsFromFilters(filters: LiveRuntimeFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.limit !== undefined && filters.limit !== DEFAULT_LIMIT) {
    params.set('limit', String(filters.limit))
  }
  if (filters.worker_id) {
    params.set('worker_id', filters.worker_id)
  }
  if (filters.event_type) {
    params.set('event_type', filters.event_type)
  }
  if (filters.symbol_key) {
    params.set('symbol_key', filters.symbol_key)
  }
  return params
}

export function RuntimePage() {
  const { platformSettings, appearance } = useSettings()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams])
  const [data, setData] = useState<LiveRuntimeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null)
  const [pollGeneration, setPollGeneration] = useState(0)

  const timezone = platformSettings.platform_behavior.timezone
  const timeDisplayFormat = appearance.time_display_format
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  const loadRuntime = useCallback(async (activeFilters: LiveRuntimeFilters, isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    try {
      const response = await fetchLiveRuntime(activeFilters)
      setData(response)
      setLastUpdatedAt(new Date().toISOString())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runtime')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void loadRuntime(filters, false)
  }, [filters, loadRuntime])

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== 'visible') {
        return
      }
      void loadRuntime(filters, true)
    }

    const timer = window.setInterval(refresh, refreshIntervalMs)
    return () => {
      window.clearInterval(timer)
    }
  }, [filters, loadRuntime, refreshIntervalMs, pollGeneration])

  function handleFiltersChange(nextFilters: LiveRuntimeFilters) {
    setSearchParams(searchParamsFromFilters(nextFilters), { replace: true })
  }

  function handleManualRefresh() {
    setPollGeneration((value) => value + 1)
    void loadRuntime(filters, true)
  }

  const workerOptions = useMemo(() => {
    const ids = new Set<string>()
    data?.state.workers.forEach((worker) => ids.add(worker.worker_id))
    data?.events.forEach((event) => ids.add(event.worker_id))
    return Array.from(ids).sort()
  }, [data])

  if (loading && !data) {
    return (
      <Stack sx={{ py: 8, alignItems: 'center' }} spacing={2}>
        <CircularProgress />
        <Typography color="text.secondary">Loading runtime…</Typography>
      </Stack>
    )
  }

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
      >
        <Box>
          <Typography variant="h4" component="h1">
            Runtime
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            Live controller and worker activity.
          </Typography>
          {lastUpdatedAt && (
            <Typography color="text.secondary" variant="caption" sx={{ display: 'block', mt: 0.5 }}>
              Last updated{' '}
              {formatInTimezone(lastUpdatedAt, timezone, timeDisplayFormat, true)}
            </Typography>
          )}
        </Box>
        <Button
          variant="outlined"
          startIcon={refreshing ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={handleManualRefresh}
          disabled={refreshing}
        >
          Refresh
        </Button>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {data && (
        <>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>
              Current state
            </Typography>
            <RuntimeStatePanel
              state={data.state}
              timezone={timezone}
              timeDisplayFormat={timeDisplayFormat}
            />
          </Paper>

          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>
              Event log
            </Typography>
            <RuntimeEventsTable
              events={data.events}
              filters={filters}
              workerOptions={workerOptions}
              timezone={timezone}
              timeDisplayFormat={timeDisplayFormat}
              onFiltersChange={handleFiltersChange}
            />
          </Paper>
        </>
      )}
    </Stack>
  )
}
