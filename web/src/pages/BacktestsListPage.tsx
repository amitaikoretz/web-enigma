import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Link,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { backtestConfigUrl, backtestReportUrl, deleteBacktest, fetchBacktests } from '../api/backtests'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useSettings } from '../settings/useSettings'
import type { BacktestListItem } from '../types/backtests'
import { formatInTimezone } from '../utils/datetime'

export function BacktestsListPage() {
  const navigate = useNavigate()
  const { platformSettings, appearance } = useSettings()
  const [items, setItems] = useState<BacktestListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<BacktestListItem | null>(null)
  const hasActiveJobs = useMemo(
    () => items.some((item) => item.status === 'pending' || item.status === 'running'),
    [items],
  )
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  useEffect(() => {
    let cancelled = false
    fetchBacktests()
      .then((response) => {
        if (!cancelled) {
          setItems(response)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load backtests')
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
        const response = await fetchBacktests()
        if (!cancelled) {
          setItems(response)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh backtests')
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

  async function confirmDelete() {
    if (!deleteTarget) {
      return
    }

    const backtestId = deleteTarget.id
    setDeletingId(backtestId)
    setError(null)
    try {
      await deleteBacktest(backtestId)
      setItems((current) => current.filter((item) => item.id !== backtestId))
      setDeleteTarget(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete backtest')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1}
        sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
      >
        <BoxSection title="Backtest Results" subtitle="Track recent jobs and open any saved analysis." />
        <Button component={RouterLink} to="/backtests/new" variant="contained">
          New backtest
        </Button>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper sx={{ p: 0, overflow: 'hidden' }}>
        {loading ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <CircularProgress />
            <Typography color="text.secondary">Loading backtests…</Typography>
          </Stack>
        ) : items.length === 0 ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <Typography variant="h6">No saved backtests yet</Typography>
            <Typography color="text.secondary">
              Run a backtest from the wizard and it will appear here.
            </Typography>
          </Stack>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Created</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Report</TableCell>
                <TableCell>Date range</TableCell>
                <TableCell>Universe</TableCell>
                <TableCell>Runs</TableCell>
                <TableCell>JSON</TableCell>
                <TableCell>YAML</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => {
                const hasReport = item.status === 'completed'
                const isDeleting = deletingId === item.id
                const isActive = item.status === 'pending' || item.status === 'running'
                const progressValue =
                  item.total_runs === 0 ? 0 : (item.completed_runs / item.total_runs) * 100

                return (
                  <TableRow
                    key={item.id}
                    hover
                    sx={{ cursor: isDeleting ? 'default' : 'pointer' }}
                    onClick={() => {
                      if (!isDeleting) {
                        navigate(`/backtests/${item.id}`)
                      }
                    }}
                  >
                    <TableCell>
                      {formatTimestamp(
                        item.created_at,
                        platformSettings.platform_behavior.timezone,
                        appearance.time_display_format,
                      )}
                    </TableCell>
                    <TableCell>
                      <BacktestStatusChip status={item.status} />
                    </TableCell>
                    <TableCell>
                      {item.report_status ? <ReportStatusChip status={item.report_status} /> : '—'}
                    </TableCell>
                    <TableCell>
                      {item.selection
                        ? `${item.selection.start_date} → ${item.selection.end_date}`
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {item.selection
                        ? `${item.selection.symbols.length} symbols / ${item.selection.strategies.length} strategies`
                        : '—'}
                    </TableCell>
                    <TableCell sx={{ minWidth: 160 }}>
                      {isActive ? (
                        <Stack spacing={0.75}>
                          <Typography variant="body2" color="text.secondary">
                            {item.completed_runs}/{item.total_runs}
                          </Typography>
                          <LinearProgress
                            variant={item.total_runs === 0 ? 'indeterminate' : 'determinate'}
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
                        `${item.completed_runs}/${item.total_runs}`
                      )}
                    </TableCell>
                    <TableCell>
                      {hasReport ? (
                        <Link
                          href={backtestReportUrl(item.id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {item.id.slice(0, 8)}.json
                        </Link>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      {hasReport ? (
                        <Link
                          href={backtestConfigUrl(item.id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {item.id.slice(0, 8)}.yaml
                        </Link>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Delete backtest">
                        <span>
                          <IconButton
                            aria-label="Delete backtest"
                            color="error"
                            disabled={isDeleting}
                            onClick={(event) => {
                              event.stopPropagation()
                              setDeleteTarget(item)
                            }}
                            size="small"
                          >
                            {isDeleting ? <CircularProgress size={18} /> : <DeleteOutlineIcon />}
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </Paper>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete backtest?"
        description={
          deleteTarget ? (
            <Stack spacing={1.5}>
              <Typography color="text.secondary">
                This permanently removes the backtest job, its JSON report, and YAML config. This
                action cannot be undone.
              </Typography>
              <Box
                sx={{
                  px: 1.5,
                  py: 1.25,
                  borderRadius: 1,
                  border: 1,
                  borderColor: 'divider',
                  bgcolor: 'action.hover',
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {deleteTarget.selection
                    ? `${deleteTarget.selection.start_date} → ${deleteTarget.selection.end_date}`
                    : 'Selection summary unavailable'}
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {deleteTarget.selection
                    ? `${deleteTarget.selection.symbols.length} symbols · ${deleteTarget.selection.strategies.length} strategies`
                    : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  {deleteTarget.id}
                </Typography>
              </Box>
            </Stack>
          ) : null
        }
        confirmLabel="Delete backtest"
        cancelLabel="Keep backtest"
        loading={deleteTarget !== null && deletingId === deleteTarget.id}
        onCancel={() => {
          if (deletingId === null) {
            setDeleteTarget(null)
          }
        }}
        onConfirm={() => {
          void confirmDelete()
        }}
      />
    </Stack>
  )
}

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat)
}

function BoxSection({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="h4">{title}</Typography>
      <Typography color="text.secondary">{subtitle}</Typography>
    </Stack>
  )
}
