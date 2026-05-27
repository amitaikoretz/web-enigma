import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
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
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { resolveVisibleColumns } from '../backtests/resultsTableColumns'
import { deleteBacktest, fetchBacktests } from '../api/backtests'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useSettings } from '../settings/useSettings'
import type { BacktestListItem } from '../types/backtests'

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
                  const isSelected = selectedIds.has(item.id)

                  return (
                    <TableRow
                      key={item.id}
                      hover
                      selected={isSelected}
                      sx={{ cursor: isDeleting ? 'default' : 'pointer' }}
                      onClick={() => {
                        if (!isDeleting) {
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
                    ? `${deleteTarget.selection.symbols?.length ?? 0} symbols · ${deleteTarget.selection.strategies?.length ?? 0} strategies`
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
