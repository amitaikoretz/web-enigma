import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import {
  Alert,
  Button,
  CircularProgress,
  IconButton,
  Link,
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
import { useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { backtestReportUrl, deleteBacktest, fetchBacktests } from '../api/backtests'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
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

  async function handleDelete(backtestId: string) {
    const confirmed = window.confirm('Delete this backtest and its JSON report?')
    if (!confirmed) {
      return
    }

    setDeletingId(backtestId)
    setError(null)
    try {
      await deleteBacktest(backtestId)
      setItems((current) => current.filter((item) => item.id !== backtestId))
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
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => {
                const hasReport = item.status === 'completed'
                const isDeleting = deletingId === item.id

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
                      {item.selection.start_date} → {item.selection.end_date}
                    </TableCell>
                    <TableCell>
                      {item.selection.symbols.length} symbols / {item.selection.strategies.length} strategies
                    </TableCell>
                    <TableCell>
                      {item.completed_runs}/{item.total_runs}
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
                    <TableCell align="right">
                      <Tooltip title="Delete backtest">
                        <span>
                          <IconButton
                            aria-label="Delete backtest"
                            color="error"
                            disabled={isDeleting}
                            onClick={(event) => {
                              event.stopPropagation()
                              void handleDelete(item.id)
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
