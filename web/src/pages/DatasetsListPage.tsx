import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  IconButton,
  Paper,
  Tab,
  Tabs,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
  LinearProgress,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { deleteDataset, fetchDatasets } from '../api/datasets'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DatasetStatusChip } from '../components/DatasetStatusChip'
import { useSettings } from '../settings/useSettings'
import type { DatasetListItem } from '../types/datasets'
import { formatInTimezone } from '../utils/datetime'
import { familyWizardPath } from './modelLaunchRoutes'

export function DatasetsListPage() {
  const navigate = useNavigate()
  const { platformSettings, appearance } = useSettings()
  const [items, setItems] = useState<DatasetListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [deleteTarget, setDeleteTarget] = useState<DatasetListItem | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const selectedOnPageCount = useMemo(
    () => items.filter((item) => selectedIds.has(item.id)).length,
    [items, selectedIds],
  )
  const allOnPageSelected = items.length > 0 && selectedOnPageCount === items.length
  const someOnPageSelected = selectedOnPageCount > 0 && !allOnPageSelected

  useEffect(() => {
    let cancelled = false
    setSelectedIds(new Set())
    setLoading(true)
    fetchDatasets()
      .then((response) => {
        if (!cancelled) {
          setItems(response.items ?? [])
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load datasets')
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

  async function refreshDatasets() {
    const response = await fetchDatasets()
    setItems(response.items ?? [])
  }

  async function confirmDelete() {
    if (!deleteTarget) {
      return
    }

    setDeletingId(deleteTarget.id)
    setError(null)
    try {
      await deleteDataset(deleteTarget.id)
      setDeleteTarget(null)
      setSelectedIds((current) => {
        const next = new Set(current)
        next.delete(deleteTarget.id)
        return next
      })
      await refreshDatasets()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete dataset')
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

    for (const datasetId of ids) {
      try {
        await deleteDataset(datasetId)
      } catch {
        failedIds.push(datasetId)
      }
    }

    setSelectedIds(new Set(failedIds))
    setBulkDeleteOpen(false)

    try {
      await refreshDatasets()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh datasets')
    } finally {
      setBulkDeleting(false)
    }

    if (failedIds.length > 0) {
      setError(`Deleted ${ids.length - failedIds.length} dataset(s). Failed to delete ${failedIds.length}.`)
    }
  }

  function launchModel(family: 'risk' | 'return_forecast' | 'daily_index_forecast') {
    const sourceIds = items.filter((item) => selectedIds.has(item.id)).map((item) => item.id)
    if (sourceIds.length === 0) {
      return
    }
    if (family === 'daily_index_forecast' && sourceIds.length !== 1) {
      return
    }

    navigate(familyWizardPath(family), {
      state: {
        sourceKind: 'dataset',
        sourceIds,
        selectedCount: sourceIds.length,
        selectionLabel: 'datasets',
        dailyIndexDatasetSource:
          family === 'daily_index_forecast'
            ? {
                symbol: items.find((item) => item.id === sourceIds[0])?.symbol ?? '',
                start_date: items.find((item) => item.id === sourceIds[0])?.start_date ?? '',
                end_date: items.find((item) => item.id === sourceIds[0])?.end_date ?? '',
              }
            : null,
      },
    })
  }

  function toggleRowSelection(datasetId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(datasetId)
      } else {
        next.delete(datasetId)
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
      <Tabs value="datasets" onChange={(_, value) => navigate(value === 'datasets' ? '/backtests/datasets' : '/backtests')} aria-label="Backtests sections">
        <Tab value="backtests" label="Backtests" />
        <Tab value="datasets" label="Datasets" />
      </Tabs>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ justifyContent: 'space-between' }}>
        <Stack spacing={0.5}>
          <Typography variant="h4">Datasets</Typography>
          <Typography color="text.secondary">
            Build parquet-backed market datasets from a date range, resolution, symbol, and provider.
          </Typography>
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="outlined"
            disabled={selectedOnPageCount === 0 || bulkDeleting}
            onClick={() => launchModel('risk')}
          >
            Train risk model{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button
            variant="outlined"
            disabled={selectedOnPageCount === 0 || bulkDeleting}
            onClick={() => launchModel('return_forecast')}
          >
            Train return forecast{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button
            variant="outlined"
            disabled={selectedOnPageCount !== 1 || bulkDeleting}
            onClick={() => launchModel('daily_index_forecast')}
          >
            Train daily index forecast{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button
            color="error"
            variant="outlined"
            disabled={selectedOnPageCount === 0 || bulkDeleting}
            onClick={() => setBulkDeleteOpen(true)}
          >
            Delete selected{selectedOnPageCount > 0 ? ` (${selectedOnPageCount})` : ''}
          </Button>
          <Button component={RouterLink} to="/backtests/datasets/new" variant="contained">
            New dataset
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper sx={{ p: 0, overflow: 'hidden' }}>
        {loading ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <CircularProgress />
            <Typography color="text.secondary">Loading datasets…</Typography>
          </Stack>
        ) : items.length === 0 ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
            <Typography variant="h6">No datasets yet</Typography>
            <Typography color="text.secondary">
              Launch a dataset job and it will appear here with workflow status and parquet paths.
            </Typography>
          </Stack>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={allOnPageSelected}
                    indeterminate={someOnPageSelected}
                    aria-label="Select all datasets on this page"
                    onChange={(_event, checked) => toggleSelectAllOnPage(checked)}
                  />
                </TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Symbol</TableCell>
                <TableCell>Provider</TableCell>
                <TableCell>Range</TableCell>
                <TableCell sx={{ minWidth: 180 }}>Progress</TableCell>
                <TableCell>Resolution</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => {
                const isDeleting = deletingId === item.id
                return (
                  <TableRow
                    key={item.id}
                    hover
                    sx={{ cursor: isDeleting ? 'default' : 'pointer' }}
                    onClick={() => {
                      if (!isDeleting) {
                        navigate(`/backtests/datasets/${item.id}`)
                      }
                    }}
                  >
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selectedIds.has(item.id)}
                        disabled={isDeleting}
                        aria-label={`Select dataset ${item.id}`}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(_event, checked) => toggleRowSelection(item.id, checked)}
                      />
                    </TableCell>
                    <TableCell>
                      {formatInTimezone(
                        item.created_at,
                        platformSettings.platform_behavior.timezone,
                        appearance.time_display_format,
                      )}
                    </TableCell>
                    <TableCell>{item.name ?? '—'}</TableCell>
                    <TableCell>
                      <DatasetStatusChip status={item.status} />
                    </TableCell>
                    <TableCell>{item.symbol}</TableCell>
                    <TableCell>{item.provider}</TableCell>
                    <TableCell>
                      {item.start_date} to {item.end_date}
                    </TableCell>
                    <TableCell sx={{ minWidth: 180 }}>
                      {item.status === 'pending' || item.status === 'running' ? (
                        <Stack spacing={0.75}>
                          <Typography variant="body2" color="text.secondary">
                            Running…
                          </Typography>
                          <LinearProgress
                            variant="indeterminate"
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
                        <Stack spacing={0.75}>
                          <Typography variant="body2" color="text.secondary">
                            {Math.round(item.progress_pct ?? 100)}% complete
                          </Typography>
                          <LinearProgress
                            variant="determinate"
                            value={Math.max(0, Math.min(100, item.progress_pct ?? 100))}
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
                      )}
                    </TableCell>
                    <TableCell>{item.resolution}</TableCell>
                    <TableCell align="right">
                      <Tooltip title="Delete dataset">
                        <span>
                          <IconButton
                            aria-label="Delete dataset"
                            color="error"
                            disabled={isDeleting || bulkDeleting}
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
        title="Delete dataset?"
        description={
          deleteTarget ? (
            <Stack spacing={1.5}>
              <Typography color="text.secondary">
                This permanently removes the dataset record and its parquet artifacts.
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
                  {deleteTarget.symbol} · {deleteTarget.provider} · {deleteTarget.resolution}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  {deleteTarget.id}
                </Typography>
              </Box>
            </Stack>
          ) : null
        }
        confirmLabel="Delete dataset"
        cancelLabel="Keep dataset"
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
        title={`Delete ${selectedOnPageCount} dataset${selectedOnPageCount === 1 ? '' : 's'}?`}
        description={
          <Typography color="text.secondary">
            This permanently removes the selected dataset records and their parquet artifacts.
            This action cannot be undone.
          </Typography>
        }
        confirmLabel={`Delete ${selectedOnPageCount}`}
        cancelLabel="Keep datasets"
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
