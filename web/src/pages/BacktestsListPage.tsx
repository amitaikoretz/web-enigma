import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Tooltip,
  TextField,
  Typography,
  Link,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { resolveVisibleColumns } from '../backtests/resultsTableColumns'
import { deleteBacktest, fetchBacktests, retryBacktest, retryBacktestForce } from '../api/backtests'
import { createRiskModel } from '../api/riskModels'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useSettings } from '../settings/useSettings'
import type { BacktestListItem } from '../types/backtests'
import { canRetryBacktest } from '../utils/backtestConfigPrefill'

interface LaunchResultState {
  status: 'success' | 'failed'
  message: string
  backtestId?: string
}

const DEFAULT_PAGE_SIZE = 25
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

function parsePage(value: string | null): number {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 1) {
    return 1
  }
  return parsed
}

function parsePageSize(value: string | null): number {
  const parsed = Number(value)
  if (PAGE_SIZE_OPTIONS.includes(parsed)) {
    return parsed
  }
  return DEFAULT_PAGE_SIZE
}

function searchParamsFromPagination(page: number, pageSize: number): URLSearchParams {
  const params = new URLSearchParams()
  if (page > 1) {
    params.set('page', String(page))
  }
  if (pageSize !== DEFAULT_PAGE_SIZE) {
    params.set('page_size', String(pageSize))
  }
  return params
}

export function BacktestsListPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const { platformSettings, appearance } = useSettings()
  const page = parsePage(searchParams.get('page'))
  const pageSize = parsePageSize(searchParams.get('page_size'))

  const [items, setItems] = useState<BacktestListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<BacktestListItem | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [retryTarget, setRetryTarget] = useState<BacktestListItem | null>(null)
  const [riskDialogOpen, setRiskDialogOpen] = useState(false)
  const [riskSubmitting, setRiskSubmitting] = useState(false)
  const [riskRandomSeed, setRiskRandomSeed] = useState('7')
  const [launchResult, setLaunchResult] = useState<LaunchResultState | null>(null)

  const visibleColumns = useMemo(
    () =>
      resolveVisibleColumns(platformSettings.backtest_defaults?.results_table_columns),
    [platformSettings.backtest_defaults?.results_table_columns],
  )
  const columnContext = useMemo(
    () => ({
      timezone: platformSettings.platform_behavior.timezone,
      timeDisplayFormat: appearance.time_display_format,
      nowMs,
    }),
    [appearance.time_display_format, nowMs, platformSettings.platform_behavior.timezone],
  )

  const hasActiveJobs = useMemo(
    () => items.some((item) => item.status === 'pending' || item.status === 'running'),
    [items],
  )
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  const selectedOnPageCount = useMemo(
    () => items.filter((item) => selectedIds.has(item.id)).length,
    [items, selectedIds],
  )
  const allOnPageSelected = items.length > 0 && selectedOnPageCount === items.length
  const someOnPageSelected = selectedOnPageCount > 0 && !allOnPageSelected

  const updatePagination = useCallback(
    (nextPage: number, nextPageSize: number) => {
      setSearchParams(searchParamsFromPagination(nextPage, nextPageSize), { replace: true })
    },
    [setSearchParams],
  )

  const loadPage = useCallback(
    async (targetPage: number, targetPageSize: number) => {
      const response = await fetchBacktests({ page: targetPage, pageSize: targetPageSize })
      const pageItems = response.items ?? []
      if (pageItems.length === 0 && response.total > 0 && targetPage > 1) {
        const lastPage = Math.max(1, Math.ceil(response.total / targetPageSize))
        updatePagination(lastPage, targetPageSize)
        return loadPage(lastPage, targetPageSize)
      }
      setItems(pageItems)
      setTotal(response.total)
      setNowMs(Date.now())
      return response
    },
    [updatePagination],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setSelectedIds(new Set())

    void loadPage(page, pageSize)
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
  }, [loadPage, page, pageSize])

  useEffect(() => {
    const state = location.state as { launchResult?: LaunchResultState } | null
    if (!state?.launchResult) {
      return
    }

    setLaunchResult(state.launchResult)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [location.pathname, location.search, location.state, navigate])

  useEffect(() => {
    if (!hasActiveJobs) {
      return undefined
    }

    let cancelled = false

    const refresh = async () => {
      try {
        await loadPage(page, pageSize)
        if (!cancelled) {
          setError(null)
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
  }, [hasActiveJobs, loadPage, page, pageSize, refreshIntervalMs])

  async function handleRetry(item: BacktestListItem) {
    setRetryingId(item.id)
    setError(null)
    try {
      const isActive = item.status === 'pending' || item.status === 'running'
      const response = isActive ? await retryBacktestForce(item.id) : await retryBacktest(item.id)
      navigate(`/backtests/${response.backtest_id}`, {
        state: { retriedFrom: item.id },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry backtest')
    } finally {
      setRetryingId(null)
      setRetryTarget((current) => (current?.id === item.id ? null : current))
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) {
      return
    }

    const backtestId = deleteTarget.id
    setDeletingId(backtestId)
    setError(null)
    try {
      await deleteBacktest(backtestId)
      setDeleteTarget(null)
      setSelectedIds((current) => {
        const next = new Set(current)
        next.delete(backtestId)
        return next
      })
      await loadPage(page, pageSize)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete backtest')
    } finally {
      setDeletingId(null)
    }
  }

  async function confirmBulkDelete() {
    const ids = items.filter((item) => selectedIds.has(item.id)).map((item) => item.id)
    if (ids.length === 0) {
      return
    }

    setBulkDeleting(true)
    setError(null)
    const failedIds: string[] = []

    for (const backtestId of ids) {
      try {
        await deleteBacktest(backtestId)
      } catch {
        failedIds.push(backtestId)
      }
    }

    const succeeded = ids.filter((id) => !failedIds.includes(id))
    setSelectedIds(new Set(failedIds))
    setBulkDeleteOpen(false)

    if (failedIds.length > 0) {
      setError(`Deleted ${succeeded.length} backtest(s). Failed to delete ${failedIds.length}.`)
    }

    try {
      await loadPage(page, pageSize)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh backtests')
    } finally {
      setBulkDeleting(false)
    }
  }

  async function submitRiskModel() {
    const ids = items.filter((item) => selectedIds.has(item.id)).map((item) => item.id)
    if (ids.length === 0) {
      return
    }
    setRiskSubmitting(true)
    setError(null)
    try {
      await createRiskModel({
        backtest_ids: ids,
        targets: [
          { target_key: 'stop_prob', task_type: 'classification' },
          { target_key: 'mae', task_type: 'regression' },
        ],
        dataset_config: {},
        train_config: { random_seed: Number(riskRandomSeed) || 7 },
      })
      setRiskDialogOpen(false)
      navigate('/risk-models')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create risk model')
    } finally {
      setRiskSubmitting(false)
    }
  }

  function toggleRowSelection(backtestId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(backtestId)
      } else {
        next.delete(backtestId)
      }
      return next
    })
  }

  function toggleSelectAllOnPage(checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current)
      for (const item of items) {
        if (checked) {
          next.add(item.id)
        } else {
          next.delete(item.id)
        }
      }
      return next
    })
  }

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1}
        sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
      >
        <BoxSection title="Backtest Results" subtitle="Track recent jobs and open any saved analysis." />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="outlined"
            disabled={selectedOnPageCount === 0 || bulkDeleting}
            onClick={() => setRiskDialogOpen(true)}
          >
            Train risk model{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button
            color="error"
            variant="outlined"
            disabled={selectedOnPageCount === 0 || bulkDeleting}
            onClick={() => setBulkDeleteOpen(true)}
          >
            Delete selected{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button component={RouterLink} to="/backtests/new" variant="contained">
            New backtest
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Dialog
        open={launchResult !== null}
        onClose={() => setLaunchResult(null)}
        aria-labelledby="launch-result-title"
        aria-describedby="launch-result-description"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(6px)',
              backgroundColor: 'rgba(0, 0, 0, 0.55)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              maxWidth: 520,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="launch-result-title" sx={{ pb: 1 }}>
          {launchResult?.status === 'success' ? 'Backtest launched' : 'Backtest launch failed'}
        </DialogTitle>
        <DialogContent id="launch-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={launchResult?.status === 'success' ? 'success' : 'error'}>
              {launchResult?.message}
            </Alert>
            {launchResult?.status === 'success' && launchResult.backtestId && (
              <Typography color="text.secondary">
                You can open the new job from{' '}
                <Link component={RouterLink} to={`/backtests/${launchResult.backtestId}`}>
                  backtest {launchResult.backtestId}
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1 }}>
          <Button onClick={() => setLaunchResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Paper sx={{ p: 0, overflow: 'hidden' }}>
        {loading ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <CircularProgress />
            <Typography color="text.secondary">Loading backtests…</Typography>
          </Stack>
        ) : total === 0 ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <Typography variant="h6">No saved backtests yet</Typography>
            <Typography color="text.secondary">
              Run a backtest from the wizard and it will appear here.
            </Typography>
          </Stack>
        ) : (
          <>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={allOnPageSelected}
                      indeterminate={someOnPageSelected}
                      aria-label="Select all backtests on this page"
                      onChange={(_event, checked) => toggleSelectAllOnPage(checked)}
                    />
                  </TableCell>
                  {visibleColumns.map((column) => (
                    <TableCell
                      key={column.id}
                      align={column.align}
                      sx={column.minWidth ? { minWidth: column.minWidth } : undefined}
                    >
                      {column.label}
                    </TableCell>
                  ))}
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((item) => {
                  const isDeleting = deletingId === item.id
                  const isRetrying = retryingId === item.id
                  const isSelected = selectedIds.has(item.id)
                  const showRetry = canRetryBacktest(item)
                  const isActive = item.status === 'pending' || item.status === 'running'

                  return (
                    <TableRow
                      key={item.id}
                      hover
                      selected={isSelected}
                      sx={{ cursor: isDeleting || isRetrying ? 'default' : 'pointer' }}
                      onClick={() => {
                        if (!isDeleting && !isRetrying) {
                          navigate(`/backtests/${item.id}`)
                        }
                      }}
                    >
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={isSelected}
                          disabled={isDeleting}
                          aria-label={`Select backtest ${item.id}`}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(_event, checked) => toggleRowSelection(item.id, checked)}
                        />
                      </TableCell>
                      {visibleColumns.map((column) => (
                        <TableCell
                          key={column.id}
                          align={column.align}
                          sx={column.minWidth ? { minWidth: column.minWidth } : undefined}
                        >
                          {column.render(item, columnContext)}
                        </TableCell>
                      ))}
                      <TableCell align="right">
                        <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                          {showRetry && (
                            <Tooltip title={isActive ? 'Run again from same configuration' : 'Retry with same configuration'}>
                              <span>
                                <IconButton
                                  aria-label="Retry backtest"
                                  disabled={isDeleting || isRetrying}
                                  onClick={(event) => {
                                    event.stopPropagation()
                                    setRetryTarget(item)
                                  }}
                                  size="small"
                                >
                                  {isRetrying ? (
                                    <CircularProgress size={18} />
                                  ) : (
                                    <ReplayIcon fontSize="small" />
                                  )}
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                          <Tooltip title="Delete backtest">
                            <span>
                              <IconButton
                                aria-label="Delete backtest"
                                color="error"
                                disabled={isDeleting || isRetrying}
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
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            <TablePagination
              component="div"
              count={total}
              page={page - 1}
              onPageChange={(_event, nextPage) => updatePagination(nextPage + 1, pageSize)}
              rowsPerPage={pageSize}
              onRowsPerPageChange={(event) =>
                updatePagination(1, parsePageSize(event.target.value))
              }
              rowsPerPageOptions={PAGE_SIZE_OPTIONS}
            />
          </>
        )}
      </Paper>

      <Dialog
        open={riskDialogOpen}
        onClose={() => {
          if (!riskSubmitting) {
            setRiskDialogOpen(false)
          }
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Train risk model</DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          <Stack spacing={2}>
            <Typography color="text.secondary">
              Trains stop probability + MAE models from the selected backtests via Argo.
            </Typography>
            <Typography>
              Selected backtests on this page: <b>{selectedOnPageCount}</b>
            </Typography>
            <TextField
              label="Random seed"
              value={riskRandomSeed}
              onChange={(e) => setRiskRandomSeed(e.target.value)}
              size="small"
              helperText="Used for walk-forward fold configuration in v1."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRiskDialogOpen(false)} disabled={riskSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={() => void submitRiskModel()}
            variant="contained"
            disabled={riskSubmitting || selectedOnPageCount === 0}
          >
            {riskSubmitting ? 'Submitting…' : 'Start training'}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={retryTarget !== null}
        title={retryTarget && (retryTarget.status === 'pending' || retryTarget.status === 'running') ? 'Run again?' : 'Retry backtest?'}
        intent="info"
        icon={<ReplayIcon sx={{ fontSize: 24 }} />}
        description={
          retryTarget ? (
            <Stack spacing={1.5}>
              <Typography color="text.secondary">
                This will start a new backtest using the same configuration. The existing run (if any) will not be stopped.
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
                  {retryTarget.selection
                    ? `${retryTarget.selection.start_date} → ${retryTarget.selection.end_date}`
                    : 'Selection summary unavailable'}
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {retryTarget.selection
                    ? `${retryTarget.selection.symbols?.length ?? 0} symbols · ${retryTarget.selection.triggers?.length ?? 0} triggers`
                    : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  {retryTarget.id}
                </Typography>
              </Box>
            </Stack>
          ) : null
        }
        confirmLabel={retryTarget && (retryTarget.status === 'pending' || retryTarget.status === 'running') ? 'Run again' : 'Retry backtest'}
        cancelLabel="Cancel"
        loading={retryTarget !== null && retryingId === retryTarget.id}
        onCancel={() => {
          if (retryingId === null) {
            setRetryTarget(null)
          }
        }}
        onConfirm={() => {
          if (retryTarget) {
            void handleRetry(retryTarget)
          }
        }}
      />

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
                    ? `${deleteTarget.selection.symbols?.length ?? 0} symbols · ${deleteTarget.selection.triggers?.length ?? 0} triggers`
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

      <ConfirmDialog
        open={bulkDeleteOpen}
        title={`Delete ${selectedOnPageCount} backtest${selectedOnPageCount === 1 ? '' : 's'}?`}
        description={
          <Typography color="text.secondary">
            This permanently removes the selected backtest jobs, their JSON reports, and YAML
            configs. This action cannot be undone.
          </Typography>
        }
        confirmLabel={`Delete ${selectedOnPageCount}`}
        cancelLabel="Keep backtests"
        loading={bulkDeleting}
        onCancel={() => {
          if (!bulkDeleting) {
            setBulkDeleteOpen(false)
          }
        }}
        onConfirm={() => {
          void confirmBulkDelete()
        }}
      />
    </Stack>
  )
}

function BoxSection({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="h4">{title}</Typography>
      <Typography color="text.secondary">{subtitle}</Typography>
    </Stack>
  )
}
