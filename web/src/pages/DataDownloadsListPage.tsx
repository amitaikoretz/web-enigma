import {
  Alert,
  Button,
  CircularProgress,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { fetchDataDownloads } from '../api/dataDownloads'
import { DataDownloadStatusChip } from '../components/DataDownloadStatusChip'
import { useSettings } from '../settings/useSettings'
import type { DataDownloadStatusResponse } from '../types/dataDownloads'
import { formatInTimezone } from '../utils/datetime'

function truncatePath(value: string, maxLength = 48): string {
  if (value.length <= maxLength) {
    return value
  }
  return `…${value.slice(-maxLength + 1)}`
}

export function DataDownloadsListPage() {
  const navigate = useNavigate()
  const { platformSettings, appearance } = useSettings()
  const [items, setItems] = useState<DataDownloadStatusResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const hasActiveJobs = useMemo(
    () => items.some((item) => item.status === 'pending' || item.status === 'running'),
    [items],
  )
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  useEffect(() => {
    let cancelled = false
    fetchDataDownloads()
      .then((response) => {
        if (!cancelled) {
          setItems(response)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load data downloads')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!hasActiveJobs) {
      return undefined
    }

    let cancelled = false

    const refresh = async () => {
      try {
        const response = await fetchDataDownloads()
        if (!cancelled) {
          setItems(response)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh data downloads')
        }
      }
    }

    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, refreshIntervalMs)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [hasActiveJobs, refreshIntervalMs])

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1}
        sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
      >
        <Stack spacing={0.5}>
          <Typography variant="h4">Market Data Downloads</Typography>
          <Typography color="text.secondary">
            Prefetch Alpaca bars into the server parquet cache before running backtests.
          </Typography>
        </Stack>
        <Button component={RouterLink} to="/data/downloads/new" variant="contained">
          New download
        </Button>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper sx={{ p: 0, overflow: 'hidden' }}>
        {loading ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <CircularProgress />
            <Typography color="text.secondary">Loading downloads…</Typography>
          </Stack>
        ) : items.length === 0 ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <Typography variant="h6">No download jobs yet</Typography>
            <Typography color="text.secondary">
              Download market data for a symbol basket and it will appear here.
            </Typography>
          </Stack>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Created</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Progress</TableCell>
                <TableCell>Result</TableCell>
                <TableCell>Cache folder</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => {
                const isActive = item.status === 'pending' || item.status === 'running'
                const progressValue =
                  item.total_records === 0 ? 0 : (item.completed_records / item.total_records) * 100

                return (
                  <TableRow
                    key={item.job_id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/data/downloads/${item.job_id}`)}
                  >
                    <TableCell>
                      {formatInTimezone(
                        item.created_at,
                        platformSettings.platform_behavior.timezone,
                        appearance.time_display_format,
                      )}
                    </TableCell>
                    <TableCell>
                      <DataDownloadStatusChip status={item.status} />
                    </TableCell>
                    <TableCell sx={{ minWidth: 160 }}>
                      {isActive ? (
                        <Stack spacing={0.75}>
                          <Typography variant="body2" color="text.secondary">
                            {item.completed_records}/{item.total_records}
                          </Typography>
                          <LinearProgress
                            variant={item.total_records === 0 ? 'indeterminate' : 'determinate'}
                            value={progressValue}
                            color="primary"
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              bgcolor: 'action.hover',
                              '& .MuiLinearProgress-bar': {
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Stack>
                      ) : (
                        `${item.completed_records}/${item.total_records}`
                      )}
                    </TableCell>
                    <TableCell>
                      {item.status === 'completed' || item.status === 'failed'
                        ? `${item.successful_records} ok · ${item.failed_records} failed`
                        : '—'}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {truncatePath(item.output_folder)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </Paper>
    </Stack>
  )
}
