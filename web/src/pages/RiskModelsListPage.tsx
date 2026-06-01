import LaunchIcon from '@mui/icons-material/Launch'
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  IconButton,
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

import { fetchRiskModelDetail, fetchRiskModels } from '../api/riskModels'
import type { RiskModelDetail, RiskModelListItem } from '../types/riskModels'
import { ConfirmDialog } from '../components/ConfirmDialog'

function statusChipColor(status: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  if (status === 'pending') return 'warning'
  return 'default'
}

export function RiskModelsListPage() {
  const [items, setItems] = useState<RiskModelListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<RiskModelDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void fetchRiskModels()
      .then((result) => {
        if (!cancelled) {
          setItems(result)
        }
      })
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

  async function openDetail(groupId: string) {
    setDetailError(null)
    try {
      const d = await fetchRiskModelDetail(groupId)
      setDetail(d)
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load risk model')
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
                  onClick={() => void openDetail(item.group_id)}
                >
                  <TableCell sx={{ fontFamily: 'monospace' }}>{item.group_id}</TableCell>
                  <TableCell>
                    <Chip size="small" label={item.status} color={statusChipColor(item.status)} />
                  </TableCell>
                  <TableCell>{item.backtest_ids.length}</TableCell>
                  <TableCell>{item.targets.join(', ')}</TableCell>
                  <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <Tooltip title="Open details">
                      <IconButton size="small" onClick={() => void openDetail(item.group_id)}>
                        <LaunchIcon fontSize="small" />
                      </IconButton>
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
    </Stack>
  )
}
