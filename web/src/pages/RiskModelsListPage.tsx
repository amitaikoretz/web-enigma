import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import LaunchIcon from '@mui/icons-material/Launch'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  IconButton,
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

import {
  deleteRiskModel,
  fetchRiskModelDetail,
  fetchRiskModelStatus,
  fetchRiskModels,
  retryRiskModel,
} from '../api/riskModels'
import type { RiskModelDetail, RiskModelListItem } from '../types/riskModels'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { RiskModelWorkflowErrorDialog } from '../components/RiskModelWorkflowErrorDialog'
import { useSettings } from '../settings/useSettings'
import {
  isRiskModelActive,
  resolveRiskModelStatus,
  statusChipColor,
} from '../utils/riskModels'

export function RiskModelsListPage() {
  const { platformSettings } = useSettings()
  const [items, setItems] = useState<RiskModelListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<RiskModelDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [workflowErrorGroupId, setWorkflowErrorGroupId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<RiskModelListItem | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)

  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  async function refreshModels() {
    const result = await fetchRiskModels()
    const activeRows = result.filter((item) => isRiskModelActive(item.status))

    if (activeRows.length === 0) {
      setItems(result)
      return result
    }

    const statusResults = await Promise.allSettled(
      activeRows.map(async (item) => ({
        groupId: item.group_id,
        status: await fetchRiskModelStatus(item.group_id),
      })),
    )

    const nextByGroup = new Map(result.map((item) => [item.group_id, item]))
    for (const resultItem of statusResults) {
      if (resultItem.status !== 'fulfilled') {
        continue
      }
      const { groupId, status } = resultItem.value
      const current = nextByGroup.get(groupId)
      if (!current) {
        continue
      }
      nextByGroup.set(groupId, {
        ...current,
        status: resolveRiskModelStatus(current.status, status.argo_phase),
      })
    }

    const merged = result.map((item) => nextByGroup.get(item.group_id) ?? item)
    setItems(merged)
    return merged
  }

  useEffect(() => {
    let cancelled = false
    // Sync the table with the latest backend status on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshModels()
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load risk models')
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

  const hasActive = useMemo(() => items.some((i) => isRiskModelActive(i.status)), [items])

  useEffect(() => {
    if (!hasActive) {
      return undefined
    }

    let cancelled = false

    const tick = async () => {
      try {
        await refreshModels()
        if (!cancelled) {
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh risk models')
        }
      }
    }

    void tick()
    const timer = window.setInterval(() => {
      void tick()
    }, refreshIntervalMs)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [hasActive, refreshIntervalMs])

  async function openDetail(groupId: string) {
    setWorkflowErrorGroupId(null)
    setDetailError(null)
    try {
      const d = await fetchRiskModelDetail(groupId)
      setDetail(d)
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load risk model')
    }
  }

  function openWorkflowErrors(groupId: string) {
    setDetailError(null)
    setDetail(null)
    setWorkflowErrorGroupId(groupId)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    const groupId = deleteTarget.group_id
    setDeletingId(groupId)
    setError(null)
    try {
      await deleteRiskModel(groupId)
      setDeleteTarget(null)
      await refreshModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete risk model')
    } finally {
      setDeletingId(null)
    }
  }

  async function retryModel(groupId: string) {
    setRetryingId(groupId)
    setError(null)
    try {
      await retryRiskModel(groupId)
      await refreshModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry risk model')
    } finally {
      setRetryingId(null)
    }
  }

  const rows = useMemo(() => items, [items])

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Risk Models</Typography>
        <Typography color="text.secondary">
          Trained models from one or more backtests. Click a row for details.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper variant="outlined">
        {loading ? (
          <Stack sx={{ py: 6, alignItems: 'center' }} spacing={1.5}>
            <CircularProgress />
            <Typography color="text.secondary">Loading risk models…</Typography>
          </Stack>
        ) : rows.length === 0 ? (
          <Box sx={{ p: 3 }}>
            <Typography color="text.secondary">No risk models yet.</Typography>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Group</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Progress</TableCell>
                <TableCell>Backtests</TableCell>
                <TableCell>Targets</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((item) => (
                <TableRow
                  key={item.group_id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() =>
                    void (item.status === 'failed'
                      ? openWorkflowErrors(item.group_id)
                      : openDetail(item.group_id))
                  }
                >
                  <TableCell sx={{ fontFamily: 'monospace' }}>{item.group_id}</TableCell>
                  <TableCell>
                    <Chip size="small" label={item.status} color={statusChipColor(item.status)} />
                  </TableCell>
                  <TableCell sx={{ minWidth: 190 }}>
                    <Stack spacing={0.5}>
                      {item.targets_total > 0 ? (
                        <>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(
                              100,
                              Math.max(0, (item.targets_done / item.targets_total) * 100),
                            )}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {item.targets_done}/{item.targets_total}
                          </Typography>
                        </>
                      ) : isRiskModelActive(item.status) ? (
                        <LinearProgress variant="indeterminate" />
                      ) : (
                        <Typography variant="caption" color="text.secondary">
                          —
                        </Typography>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>{item.backtest_ids.length}</TableCell>
                  <TableCell>{item.targets.join(', ')}</TableCell>
                  <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <Tooltip title="Open details">
                      <IconButton
                        size="small"
                        aria-label="Open details"
                        onClick={() => void openDetail(item.group_id)}
                      >
                        <LaunchIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {item.status === 'failed' && (
                      <Tooltip title="Retry training">
                        <span>
                          <IconButton
                            size="small"
                            color="warning"
                            aria-label="Retry training"
                            disabled={retryingId === item.group_id}
                            onClick={() => void retryModel(item.group_id)}
                          >
                            <ReplayIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    )}
                    <Tooltip title="Delete">
                      <span>
                        <IconButton
                          size="small"
                          color="error"
                          aria-label="Delete risk model"
                          disabled={deletingId === item.group_id}
                          onClick={() => setDeleteTarget(item)}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <ConfirmDialog
        open={detail !== null}
        title={detail ? `Risk model ${detail.group_id}` : 'Risk model'}
        intent="info"
        confirmLabel="Close"
        cancelLabel="Cancel"
        onCancel={() => setDetail(null)}
        onConfirm={() => setDetail(null)}
        description={
          <>
            {detailError && <Alert severity="error">{detailError}</Alert>}
            {detail && (
              <Stack spacing={1}>
                <Typography>
                  Status: <b>{detail.status}</b>
                </Typography>
                <Typography>
                  Backtests: <b>{detail.sources.length}</b>
                </Typography>
                <Typography sx={{ fontFamily: 'monospace' }}>Artifact dir: {detail.artifact_dir}</Typography>
                <Typography variant="subtitle2">Targets</Typography>
                <Stack spacing={0.5}>
                  {detail.targets.map((t) => (
                    <Box key={t.id} sx={{ fontFamily: 'monospace' }}>
                      {t.target_key}: {t.status}
                    </Box>
                  ))}
                </Stack>
              </Stack>
            )}
          </>
        }
      />

      <RiskModelWorkflowErrorDialog
        groupId={workflowErrorGroupId}
        open={workflowErrorGroupId !== null}
        onClose={() => setWorkflowErrorGroupId(null)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `Delete risk model ${deleteTarget.group_id}?` : 'Delete risk model'}
        intent="error"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
        loading={deleteTarget ? deletingId === deleteTarget.group_id : false}
        description={
          <Typography color="text.secondary">
            This deletes the risk model group, its DB rows, and its artifact directory. If it is running, its Argo
            workflow will be terminated best-effort.
          </Typography>
        }
      />
    </Stack>
  )
}
