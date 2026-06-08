import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import LaunchIcon from '@mui/icons-material/Launch'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Autocomplete,
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  Link,
  MenuItem,
  Paper,
  LinearProgress,
  Select,
  Stack,
  Switch,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom'

import { fetchDatasetDetail, fetchDatasets } from '../api/datasets'
import { deleteDailyIndexForecastModel, fetchDailyIndexForecastModelChartData } from '../api/dailyIndexForecastModels'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { CandlestickChart } from '../components/CandlestickChart'
import { FeatureImportanceTab } from '../components/FeatureImportanceTab'
import { ModelWorkflowErrorDialog } from '../components/ModelWorkflowErrorDialog'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import { formatMetricNumber } from '../components/BacktestMetricGrid'
import { useSettings } from '../settings/useSettings'
import { statusChipColor, isModelActive } from '../utils/modelStatus'
import { formatInTimezone } from '../utils/datetime'
import { toChartTime } from '../utils/chartTime'
import type { DatasetDetailResponse, DatasetListItem } from '../types/datasets'
import type { ModelWorkflowErrorResponse } from '../types/modelFamilies'
import type {
  DailyIndexForecastChartResponse,
  DailyIndexForecastCreateRequest,
  DailyIndexForecastDetail,
  DailyIndexForecastListItem,
  DailyIndexForecastStatusResponse,
  DailyIndexForecastWorkflowErrorResponse,
  DailyIndexForecastSplitLabel,
  DailyIndexForecastTargetRow,
} from '../types/dailyIndexForecastModels'

type MainTab = 'overview' | 'provenance' | 'performance' | 'feature-importance' | 'debug'
type MainTabWithCharts = MainTab | 'charts'
type DailyIndexForecastLaunchResultState =
  | {
      status: 'success'
      message: string
      groupId: string
      featureRunId: string
    }
  | {
      status: 'failed'
      message: string
    }

type DailyIndexForecastRetryResultState =
  | {
      status: 'success'
      message: string
      groupId: string
      featureRunId: string
    }
  | {
      status: 'failed'
      message: string
    }

const MAIN_TABS: Array<{ id: MainTabWithCharts; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'charts', label: 'Charts' },
  { id: 'provenance', label: 'Provenance' },
  { id: 'performance', label: 'Performance' },
  { id: 'feature-importance', label: 'Feature Importance' },
  { id: 'debug', label: 'Debug' },
]

function strip(value?: string | null): string {
  return value?.trim() ?? ''
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString()
}

function formatHoldoutDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: 'UTC',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(`${value}T00:00:00Z`))
}

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function formatResolution(value?: string | null): string {
  return value?.trim() || '—'
}

function formatSignedBps(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(1)} bps`
}

function splitLabelColor(splitLabel: DailyIndexForecastSplitLabel): 'success' | 'warning' | 'info' | 'default' {
  if (splitLabel === 'train') return 'success'
  if (splitLabel === 'test') return 'warning'
  if (splitLabel === 'validation') return 'info'
  return 'default'
}

function splitLabelText(splitLabel: DailyIndexForecastSplitLabel): string {
  if (splitLabel === 'other') return 'other'
  return splitLabel
}

export function chartLoadErrorDetails(message: string): { severity: 'info' | 'warning'; message: string } {
  const normalized = message.toLowerCase()
  if (
    normalized.includes('not enough sessions for walk-forward folds') ||
    normalized.includes('no walk-forward folds could be created')
  ) {
    return {
      severity: 'info',
      message:
        'This model does not have enough session history yet to build walk-forward chart data. Try an earlier date or train with a wider date range.',
    }
  }

  return { severity: 'warning', message }
}

function InfoTable({
  rows,
}: {
  rows: Array<{ label: string; value: string; mono?: boolean }>
}) {
  if (rows.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        No details available.
      </Typography>
    )
  }
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell sx={{ width: { xs: '40%', md: '28%' }, fontWeight: 700, color: 'text.secondary' }}>
                {row.label}
              </TableCell>
              <TableCell sx={{ fontFamily: row.mono ? 'monospace' : 'inherit', whiteSpace: 'pre-wrap' }}>
                {row.value}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return formatMetricNumber(value, 4)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map((item) => formatMetricValue(item)).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function flattenMetrics(value: unknown, prefix = ''): Array<{ path: string; label: string; value: string }> {
  if (!isPlainObject(value)) {
    return prefix ? [{ path: prefix, label: prefix, value: formatMetricValue(value) }] : []
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return prefix ? [{ path: prefix, label: prefix, value: '—' }] : []
  }

  const out: Array<{ path: string; label: string; value: string }> = []
  for (const [key, nextValue] of entries) {
    const path = prefix ? `${prefix}.${key}` : key
    if (isPlainObject(nextValue)) {
      out.push(...flattenMetrics(nextValue, path))
    } else {
      out.push({ path, label: path, value: formatMetricValue(nextValue) })
    }
  }
  return out
}

function sectionTitle(path: string): string {
  if (path.startsWith('holdout.')) return 'Holdout metrics'
  if (path.startsWith('aggregate.validation.')) return 'Walk-forward validation'
  if (path.startsWith('aggregate.test.')) return 'Walk-forward test'
  if (path.startsWith('aggregate.')) return 'Walk-forward aggregate'
  if (path.startsWith('walk_forward.')) return 'Walk-forward setup'
  if (path.startsWith('regression.')) return 'Regression metrics'
  if (path.startsWith('classification.')) return 'Classification metrics'
  if (path.startsWith('calibration.')) return 'Calibration metrics'
  if (path.startsWith('quantile.')) return 'Interval metrics'
  return 'Other metrics'
}

function sectionDescription(title: string): string {
  switch (title) {
    case 'Holdout metrics':
      return 'The final out-of-sample segment reserved from model selection.'
    case 'Walk-forward validation':
      return 'Validation metrics averaged across walk-forward folds.'
    case 'Walk-forward test':
      return 'Test metrics averaged across walk-forward folds.'
    case 'Walk-forward aggregate':
      return 'Fold-level aggregate metrics for the walk-forward run.'
    case 'Walk-forward setup':
      return 'How the daily sessions were sliced for evaluation.'
    case 'Regression metrics':
      return 'Forecast error on the return-to-close regression target.'
    case 'Classification metrics':
      return 'Probability-based directional metrics derived from the regression output.'
    case 'Calibration metrics':
      return 'How well predicted probabilities align with observed outcomes.'
    case 'Interval metrics':
      return 'Prediction interval coverage and width at several confidence levels.'
    default:
      return 'Additional recorded metrics.'
  }
}

function buildMetricSections(value: unknown): Array<{ title: string; description: string; rows: Array<{ path: string; label: string; value: string }> }> {
  const rows = flattenMetrics(value)
  const sections = new Map<string, Array<{ path: string; label: string; value: string }>>()
  for (const row of rows) {
    const title = sectionTitle(row.path)
    const current = sections.get(title) ?? []
    current.push(row)
    sections.set(title, current)
  }

  return [...sections.entries()].map(([title, sectionRows]) => ({
    title,
    description: sectionDescription(title),
    rows: sectionRows.sort((left, right) => left.label.localeCompare(right.label)),
  }))
}

function MetricSections({ value }: { value: unknown }) {
  const sections = buildMetricSections(value)
  if (sections.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        No metrics recorded yet.
      </Typography>
    )
  }

  return (
    <Stack spacing={1.5}>
      {sections.map((section) => (
        <Paper key={section.title} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
          <Stack spacing={1}>
            <Stack spacing={0.25}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {section.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {section.description}
              </Typography>
            </Stack>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700 }}>Metric</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {section.rows.map((row) => (
                    <TableRow key={row.path}>
                      <TableCell sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>{row.label}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{row.value}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

function parseCommaList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function datasetLabel(item: DatasetListItem): string {
  const displayName = item.name?.trim() || item.symbol
  return `${displayName} - ${item.symbol} - ${item.start_date} to ${item.end_date}`
}

function buildSourceSpec(
  symbol: string,
  sourceType: 'alpaca' | 'yahoo' | 'csv',
  interval: string,
  feed: string,
  csvPath: string,
): Record<string, unknown> {
  if (sourceType === 'csv') {
    return {
      type: 'csv',
      path: csvPath,
      datetime_column: 'datetime',
      open_column: 'open',
      high_column: 'high',
      low_column: 'low',
      close_column: 'close',
      volume_column: 'volume',
    }
  }

  if (sourceType === 'yahoo') {
    return { type: 'yahoo', symbol, interval }
  }
  return { type: 'alpaca', symbol, interval, feed }
}

export function DailyIndexForecastModelsListPage({
  fetchModels,
  fetchModelStatus,
  fetchModelWorkflowErrors,
  retryModel,
  deleteModel,
}: {
  fetchModels: () => Promise<DailyIndexForecastListItem[]>
  fetchModelStatus: (groupId: string) => Promise<DailyIndexForecastStatusResponse>
  fetchModelWorkflowErrors: (groupId: string) => Promise<DailyIndexForecastWorkflowErrorResponse>
  retryModel: (groupId: string) => Promise<{ group_id: string; feature_run_id: string }>
  deleteModel: (groupId: string) => Promise<void>
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { platformSettings } = useSettings()
  const [items, setItems] = useState<DailyIndexForecastListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorGroupId, setWorkflowErrorGroupId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DailyIndexForecastListItem | null>(null)
  const [retryTarget, setRetryTarget] = useState<DailyIndexForecastListItem | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [launchResult, setLaunchResult] = useState<DailyIndexForecastLaunchResultState | null>(null)
  const [retryResult, setRetryResult] = useState<DailyIndexForecastRetryResultState | null>(null)

  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  async function refresh() {
    const result = await fetchModels()
    const activeRows = result.filter((item) => isModelActive(item.status))
    if (activeRows.length === 0) {
      setItems(result)
      return result
    }
    const statuses = await Promise.allSettled(activeRows.map(async (item) => [item.group_id, await fetchModelStatus(item.group_id)] as const))
    const nextById = new Map(result.map((item) => [item.group_id, item]))
    for (const item of statuses) {
      if (item.status !== 'fulfilled') continue
      const [groupId, status] = item.value
      const current = nextById.get(groupId)
      if (!current) continue
      nextById.set(groupId, { ...current, status: status.argo_phase === 'Succeeded' ? 'succeeded' : current.status })
    }
    const merged = result.map((item) => nextById.get(item.group_id) ?? item)
    setItems(merged)
    return merged
  }

  useEffect(() => {
    let cancelled = false
    // The initial load intentionally kicks off async state updates for the page.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh()
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load Daily Index Forecast models')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const state = location.state as { launchResult?: DailyIndexForecastLaunchResultState } | null
    if (!state?.launchResult) {
      return
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLaunchResult(state.launchResult)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [location.pathname, location.search, location.state, navigate])

  const hasActive = useMemo(() => items.some((item) => isModelActive(item.status)), [items])

  function holdoutMaeLabel(item: DailyIndexForecastListItem): string {
    const mae = (item.summary_metrics as { holdout?: { regression?: { mae?: unknown } } } | null | undefined)?.holdout?.regression?.mae
    return mae != null ? `MAE ${formatMetricNumber(Number(mae), 3)}` : '—'
  }

  useEffect(() => {
    if (!hasActive) return undefined
    let cancelled = false
    const timer = window.setInterval(() => {
      void refresh().catch(() => {
        if (!cancelled) {
          setError('Failed to refresh Daily Index Forecast models')
        }
      })
    }, refreshIntervalMs)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActive, refreshIntervalMs])

  async function handleRetry() {
    if (!retryTarget) return
    const groupId = retryTarget.group_id
    setRetryingId(groupId)
    try {
      const response = await retryModel(groupId)
      await refresh()
      setRetryResult({
        status: 'success',
        message: 'Daily Index Forecast retry submitted successfully.',
        groupId: response.group_id,
        featureRunId: response.feature_run_id,
      })
      setRetryTarget(null)
    } catch (err) {
      setRetryResult({
        status: 'failed',
        message: err instanceof Error ? err.message : 'Failed to retry Daily Index Forecast',
      })
    } finally {
      setRetryingId(null)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeletingId(deleteTarget.group_id)
    try {
      await deleteModel(deleteTarget.group_id)
      setDeleteTarget(null)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete Daily Index Forecast')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Stack spacing={2}>
      <Dialog
        open={launchResult !== null}
        onClose={() => setLaunchResult(null)}
        aria-labelledby="daily-index-launch-result-title"
        aria-describedby="daily-index-launch-result-description"
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
        <DialogTitle id="daily-index-launch-result-title" sx={{ pb: 1 }}>
          {launchResult?.status === 'success' ? 'Daily Index Forecast launched' : 'Daily Index Forecast launch failed'}
        </DialogTitle>
        <DialogContent id="daily-index-launch-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={launchResult?.status === 'success' ? 'success' : 'error'}>
              {launchResult?.message}
            </Alert>
            {launchResult?.status === 'success' && launchResult.groupId && (
              <Typography color="text.secondary">
                You can open the new forecast from{' '}
                <Link component={RouterLink} to={`/models/daily-index/${launchResult.groupId}`}>
                  forecast {launchResult.groupId}
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={() => setLaunchResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={retryResult !== null}
        onClose={() => setRetryResult(null)}
        aria-labelledby="daily-index-retry-result-title"
        aria-describedby="daily-index-retry-result-description"
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
        <DialogTitle id="daily-index-retry-result-title" sx={{ pb: 1 }}>
          {retryResult?.status === 'success' ? 'Daily Index Forecast retry submitted' : 'Daily Index Forecast retry failed'}
        </DialogTitle>
        <DialogContent id="daily-index-retry-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={retryResult?.status === 'success' ? 'success' : 'error'}>{retryResult?.message}</Alert>
            {retryResult?.status === 'success' && retryResult.groupId && (
              <Typography color="text.secondary">
                You can open the retried forecast from{' '}
                <Link component={RouterLink} to={`/models/daily-index/${retryResult.groupId}`}>
                  forecast {retryResult.groupId}
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={() => setRetryResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Stack spacing={0.5}>
        <Typography variant="h4" component="h1">
          Daily Index Forecast
        </Typography>
        <Typography color="text.secondary">
          Research-only forecast groups with dedicated feature extraction, walk-forward evaluation, and holdout
          metrics.
        </Typography>
      </Stack>

      <Box sx={{ display: 'flex', justifyContent: 'flex-start' }}>
        <Button component={RouterLink} to="/models/daily-index/new" variant="contained">
          New forecast
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper variant="outlined">
        {loading ? (
          <Stack sx={{ py: 6, alignItems: 'center' }} spacing={1.5}>
            <CircularProgress />
            <Typography color="text.secondary">Loading Daily Index Forecasts…</Typography>
          </Stack>
        ) : items.length === 0 ? (
          <Box sx={{ p: 3 }}>
            <Typography color="text.secondary">No Daily Index Forecasts yet.</Typography>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Group</TableCell>
                <TableCell>Symbol</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Window</TableCell>
                <TableCell>Decision times</TableCell>
                <TableCell>Holdout</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.group_id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/models/daily-index/${item.group_id}`)}>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{item.group_id}</TableCell>
                  <TableCell>{item.symbol}</TableCell>
                  <TableCell>
                    <Chip size="small" label={item.status} color={statusChipColor(item.status)} />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {formatDate(item.start_date)} to {formatDate(item.end_date)}
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{item.decision_times.join(', ')}</TableCell>
                  <TableCell>
                    {holdoutMaeLabel(item)}
                  </TableCell>
                  <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <Tooltip title="Open details">
                      <IconButton size="small" onClick={() => navigate(`/models/daily-index/${item.group_id}`)}>
                        <LaunchIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Workflow errors">
                      <span>
                        <IconButton size="small" color="error" onClick={() => setWorkflowErrorGroupId(item.group_id)}>
                          <BugReportOutlinedIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="Retry">
                      <span>
                        <IconButton
                          size="small"
                          color="warning"
                          disabled={retryingId === item.group_id}
                          onClick={() => setRetryTarget(item)}
                        >
                          <ReplayIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <span>
                        <IconButton size="small" color="error" disabled={deletingId === item.group_id} onClick={() => setDeleteTarget(item)}>
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

      <ModelWorkflowErrorDialog
        groupId={workflowErrorGroupId}
        open={workflowErrorGroupId !== null}
        onClose={() => setWorkflowErrorGroupId(null)}
        entityKind="Daily Index Forecast"
        entityLabel={workflowErrorGroupId ? `Daily Index Forecast ${workflowErrorGroupId}` : 'Daily Index Forecast'}
        fetchWorkflowErrors={fetchModelWorkflowErrors as unknown as (groupId: string) => Promise<ModelWorkflowErrorResponse>}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `Delete Daily Index Forecast ${deleteTarget.group_id}?` : 'Delete Daily Index Forecast'}
        intent="error"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
        loading={deleteTarget ? deletingId === deleteTarget.group_id : false}
        description={
          <Typography color="text.secondary">
            This deletes the DB rows and artifact directories for the forecast group and its feature extraction run.
          </Typography>
        }
      />

      <ConfirmDialog
        open={retryTarget !== null}
        title={retryTarget ? `Retry Daily Index Forecast ${retryTarget.group_id}?` : 'Retry Daily Index Forecast'}
        intent="warning"
        confirmLabel="Retry"
        cancelLabel="Cancel"
        loading={retryTarget ? retryingId === retryTarget.group_id : false}
        onCancel={() => setRetryTarget(null)}
        onConfirm={() => void handleRetry()}
        description={
          <Stack spacing={1}>
            <Typography color="text.secondary">
              This will submit a new Argo workflow using the stored launch parameters for this forecast.
            </Typography>
            <Typography color="text.secondary">
              If Argo rejects the workflow, the error will be shown here instead of silently disappearing.
            </Typography>
          </Stack>
        }
      />
    </Stack>
  )
}

function renderTargetSummary(targets: DailyIndexForecastTargetRow[]) {
  if (targets.length === 0) {
    return <Typography color="text.secondary">No model targets recorded yet.</Typography>
  }
  return (
    <Stack spacing={1.5}>
      {targets.map((target) => (
        <Paper key={target.id} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
          <Stack spacing={1}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {target.target_key}
              </Typography>
              <Chip size="small" label={target.task_type} variant="outlined" />
              <Chip size="small" label={target.status} color={statusChipColor(target.status as never)} />
            </Stack>
            <InfoTable
              rows={[
                { label: 'Artifact', value: target.model_artifact_path ?? '—', mono: true },
                { label: 'Manifest', value: target.dataset_manifest_path ?? '—', mono: true },
                { label: 'Feature count', value: String(target.feature_columns?.length ?? 0) },
              ]}
            />
            {target.metrics ? <MetricSections value={target.metrics} /> : <Typography color="text.secondary">No metrics available.</Typography>}
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

export function DailyIndexForecastModelDetailPage({
  fetchModelDetail,
  fetchModelStatus,
  fetchModelWorkflowErrors,
  retryModel,
  deleteModel = deleteDailyIndexForecastModel,
  updateModelName,
}: {
  fetchModelDetail: (groupId: string) => Promise<DailyIndexForecastDetail>
  fetchModelStatus: (groupId: string) => Promise<DailyIndexForecastStatusResponse>
  fetchModelWorkflowErrors: (groupId: string) => Promise<DailyIndexForecastWorkflowErrorResponse>
  retryModel: (groupId: string) => Promise<{ group_id: string; feature_run_id: string }>
  deleteModel?: (groupId: string) => Promise<void>
  updateModelName?: (groupId: string, name: string | null) => Promise<DailyIndexForecastDetail>
}) {
  const { platformSettings, appearance } = useSettings()
  const { groupId = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<DailyIndexForecastDetail | null>(null)
  const [status, setStatus] = useState<DailyIndexForecastStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorsOpen, setWorkflowErrorsOpen] = useState(false)
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)
  const [mainTab, setMainTab] = useState<MainTabWithCharts>('overview')
  const [chartDate, setChartDate] = useState('')
  const [chartData, setChartData] = useState<DailyIndexForecastChartResponse | null>(null)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState<string | null>(null)
  const chartDataCacheRef = useRef(new Map<string, DailyIndexForecastChartResponse>())
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const timezone = platformSettings.platform_behavior.timezone
  const timeDisplayFormat = appearance.time_display_format
  const holdoutDates = detail?.holdout_dates ?? []

  function syncChartDate(nextHoldoutDates: string[]) {
    setChartDate((current) => {
      if (nextHoldoutDates.length === 0) {
        return ''
      }
      if (current && nextHoldoutDates.includes(current)) {
        return current
      }
      return nextHoldoutDates[0]
    })
  }

  useEffect(() => {
    let cancelled = false
    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchModelDetail(groupId)
        if (cancelled) return
        setDetail(response)
        syncChartDate(response.holdout_dates ?? [])
        setStatus({
          group_id: response.group_id,
          feature_run_id: response.feature_run_id,
          name: response.name,
          status: response.status,
          argo_namespace: response.argo_namespace,
          argo_workflow_name: response.argo_workflow_name,
          argo_phase: null,
          progress_pct: 0,
        })
        try {
          const nextStatus = await fetchModelStatus(groupId)
          if (!cancelled) setStatus(nextStatus)
        } catch {
          // best effort
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load Daily Index Forecast detail')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [fetchModelDetail, fetchModelStatus, groupId])

  useEffect(() => {
    // The name draft mirrors loaded detail state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNameDraft(detail?.name ?? '')
  }, [detail?.name])

  useEffect(() => {
    if (!detail) {
      return
    }
    if (holdoutDates.length === 0) {
      if (chartDate !== '') {
        setChartDate('')
      }
      setChartData(null)
      return
    }
    if (!chartDate || !holdoutDates.includes(chartDate)) {
      setChartDate(holdoutDates[0])
    }
  }, [chartDate, detail, holdoutDates])

  useEffect(() => {
    if (!groupId || !detail || !isModelActive(detail.status)) return undefined

    let cancelled = false

    const poll = async () => {
      try {
        const nextStatus = await fetchModelStatus(groupId)
        if (cancelled) {
          return true
        }

        setStatus(nextStatus)

        if (!isModelActive(nextStatus.status)) {
          const nextDetail = await fetchModelDetail(groupId)
          if (!cancelled) {
            setDetail(nextDetail)
            syncChartDate(nextDetail.holdout_dates ?? [])
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh Daily Index Forecast status')
        }
        return true
      }
    }

    let timer: ReturnType<typeof window.setInterval> | undefined
    void (async () => {
      const terminal = await poll()
      if (terminal || cancelled) {
        return
      }

      timer = window.setInterval(() => {
        void poll().then((done) => {
          if (done && timer !== undefined) {
            window.clearInterval(timer)
            timer = undefined
          }
        })
      }, refreshIntervalMs)
    })()

    return () => {
      cancelled = true
      if (timer !== undefined) {
        window.clearInterval(timer)
      }
    }
  }, [detail, fetchModelDetail, fetchModelStatus, groupId, refreshIntervalMs])

  useEffect(() => {
    const detailGroupId = detail?.group_id ?? ''
    if (!detailGroupId || mainTab !== 'charts' || !chartDate) {
      return
    }
    const cacheKey = `${detailGroupId}:${chartDate}`
    const cached = chartDataCacheRef.current.get(cacheKey)
    if (cached) {
      setChartData(cached)
      setChartError(null)
      setChartLoading(false)
      return
    }
    let cancelled = false
    setChartLoading(true)
    setChartError(null)
    fetchDailyIndexForecastModelChartData(detailGroupId, chartDate)
      .then((response) => {
        if (!cancelled) {
          chartDataCacheRef.current.set(cacheKey, response)
          setChartData(response)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setChartData(null)
          setChartError(err instanceof Error ? err.message : 'Failed to load Daily Index Forecast chart data')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChartLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [chartDate, detail?.group_id, mainTab])

  const activeStatus = status?.status ?? detail?.status ?? null
  const progressPct = activeStatus && isModelActive(activeStatus) ? status?.progress_pct ?? 0 : 100
  const isActive = activeStatus ? isModelActive(activeStatus) : false

  useEffect(() => {
    if (!groupId || !isActive) return undefined
    let cancelled = false
    const timer = window.setInterval(() => {
      void fetchModelStatus(groupId).then((nextStatus) => {
        if (!cancelled) setStatus(nextStatus)
      })
    }, refreshIntervalMs)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [fetchModelStatus, groupId, isActive, refreshIntervalMs])

  const summaryMetrics = detail?.summary_metrics ?? null
  const featureRun = detail?.feature_run ?? null
  const resolution = detail?.resolution ?? featureRun?.resolution ?? chartData?.resolution ?? null
  const chartDataResolution = chartData?.resolution ?? resolution ?? '5m'
  const chartErrorAlert = chartError ? chartLoadErrorDetails(chartError) : null
  const chartPredictions = useMemo(
    () =>
      chartData?.predictions.map((prediction) => ({
        ...prediction,
        delta_bps:
          prediction.actual_bps !== null && prediction.actual_bps !== undefined
            ? prediction.predicted_bps - prediction.actual_bps
            : null,
      })) ?? [],
    [chartData],
  )
  const chartAnnotationMarkers = useMemo(
    () =>
      chartData?.predictions.map((prediction) => ({
        time: toChartTime(prediction.decision_timestamp, chartDataResolution),
        position: 'inBar' as const,
        color: prediction.split_label === 'train' ? '#3fb950' : prediction.split_label === 'test' ? '#f0883e' : '#58a6ff',
        shape: 'circle' as const,
        text: `${prediction.decision_time} ${prediction.predicted_bps.toFixed(1)}bps`,
      })) ?? [],
    [chartData, chartDataResolution],
  )

  async function saveName() {
    if (!detail || !updateModelName) return
    setSavingName(true)
    try {
      const updated = await updateModelName(detail.group_id, strip(nameDraft) ? nameDraft : null)
      setDetail(updated)
      setRenameDialogOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update name')
    } finally {
      setSavingName(false)
    }
  }

  async function handleDelete() {
    if (!detail) return
    setDeleting(true)
    setError(null)
    try {
      await deleteModel(detail.group_id)
      setDeleteDialogOpen(false)
      navigate('/models/daily-index')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete Daily Index Forecast')
    } finally {
      setDeleting(false)
    }
  }

  async function handleRetry() {
    if (!detail) return
    setRetrying(true)
    try {
      await retryModel(detail.group_id)
      setRetryDialogOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry Daily Index Forecast')
    } finally {
      setRetrying(false)
    }
  }

  if (loading && !detail) {
    return (
      <Stack sx={{ py: 10, alignItems: 'center' }} spacing={1}>
        <CircularProgress />
        <Typography color="text.secondary">Loading Daily Index Forecast…</Typography>
      </Stack>
    )
  }

  if (error && !detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="error">{error}</Alert>
        <Button component={RouterLink} to="/models/daily-index" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to forecasts
        </Button>
      </Stack>
    )
  }

  if (!detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="warning">Daily Index Forecast detail is unavailable.</Alert>
        <Button component={RouterLink} to="/models/daily-index" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to forecasts
        </Button>
      </Stack>
    )
  }

  const detailDisplayLabel = detail.name ? `Daily Index Forecast ${detail.name}` : `Daily Index Forecast ${detail.group_id}`

  return (
    <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1fr) 360px' } }}>
      <Stack spacing={3}>
        <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3 }}>
          <Stack spacing={2}>
            <Button component={RouterLink} to="/models/daily-index" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
              Back to forecasts
            </Button>
            <Stack spacing={1.25}>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                <Stack spacing={0.25}>
                  <Typography variant="h4" component="h1">
                    {detail.name ?? detail.group_id}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                    {detail.group_id}
                  </Typography>
                </Stack>
                <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
                <Chip size="small" label={`Resolution ${formatResolution(resolution)}`} variant="outlined" />
                {updateModelName && (
                  <Button size="small" variant="outlined" onClick={() => setRenameDialogOpen(true)}>
                    Rename
                  </Button>
                )}
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  Delete
                </Button>
              </Stack>
              <Typography color="text.secondary">
                Research dashboard for a single Daily Index Forecast group, including feature provenance, holdout metrics,
                and workflow diagnostics.
              </Typography>
              <Tabs value={mainTab} onChange={(_, next) => setMainTab(next as MainTabWithCharts)} variant="scrollable" allowScrollButtonsMobile>
                {MAIN_TABS.map((tab) => (
                  <Tab key={tab.id} value={tab.id} label={tab.label} />
                ))}
              </Tabs>
            </Stack>
          </Stack>
        </Paper>

        {error && <Alert severity="error">{error}</Alert>}

        {mainTab === 'overview' && (
          <Stack spacing={2}>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Summary
                  </Typography>
                  <InfoTable
                    rows={[
                      { label: 'Symbol', value: featureRun?.symbol ?? '—' },
                      { label: 'Benchmark', value: featureRun?.benchmark_symbol ?? '—' },
                      { label: 'Resolution', value: formatResolution(resolution), mono: true },
                      { label: 'Decision times', value: featureRun?.decision_times.join(', ') || '—', mono: true },
                      { label: 'Feature run', value: detail.feature_run_id, mono: true },
                      { label: 'Feature artifact dir', value: detail.feature_run?.artifact_dir ?? '—', mono: true },
                      { label: 'Group artifact dir', value: detail.artifact_dir, mono: true },
                      { label: 'Created', value: formatTimestamp(detail.created_at, timezone, timeDisplayFormat) },
                      { label: 'Updated', value: formatTimestamp(detail.updated_at, timezone, timeDisplayFormat) },
                    ]}
                  />
                </Stack>
              </CardContent>
            </Card>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Holdout metrics
                  </Typography>
                  {summaryMetrics?.holdout ? <MetricSections value={summaryMetrics.holdout} /> : <Alert severity="info">No holdout metrics are available yet.</Alert>}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        )}

        {mainTab === 'provenance' && (
          <Stack spacing={2}>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Feature run provenance
                  </Typography>
                  {featureRun ? (
                    <InfoTable
                      rows={[
                        { label: 'Status', value: featureRun.status },
                        { label: 'Artifact dir', value: featureRun.artifact_dir, mono: true },
                        { label: 'Manifest', value: featureRun.manifest?.output_path ?? '—', mono: true },
                        { label: 'Resolution', value: formatResolution(featureRun.resolution ?? resolution), mono: true },
                        { label: 'Features parquet', value: featureRun.features_parquet_path ?? '—', mono: true },
                        { label: 'Labels parquet', value: featureRun.labels_parquet_path ?? '—', mono: true },
                        { label: 'Start date', value: featureRun.manifest?.start_date ?? '—' },
                        { label: 'End date', value: featureRun.manifest?.end_date ?? '—' },
                        { label: 'Decision times', value: featureRun.decision_times.join(', ') || '—', mono: true },
                      ]}
                    />
                  ) : (
                    <Alert severity="info">Feature run details are not available yet.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Dataset manifest
                  </Typography>
                  {detail.dataset_manifest ? (
                    <InfoTable
                      rows={[
                        { label: 'Config hash', value: detail.dataset_manifest.config_hash, mono: true },
                        { label: 'Feature rows', value: String(detail.dataset_manifest.feature_rows) },
                        { label: 'Label rows', value: String(detail.dataset_manifest.label_rows) },
                        { label: 'Joined rows', value: String(detail.dataset_manifest.joined_rows) },
                        { label: 'Dropped feature rows', value: String(detail.dataset_manifest.dropped_feature_rows) },
                        { label: 'Dropped label rows', value: String(detail.dataset_manifest.dropped_label_rows) },
                        { label: 'Feature version', value: detail.dataset_manifest.feature_version },
                        { label: 'Label version', value: detail.dataset_manifest.label_version },
                      ]}
                    />
                  ) : (
                    <Alert severity="info">No dataset manifest is available yet.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        )}

        {mainTab === 'performance' && (
          <Stack spacing={2}>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Walk-forward summary
                  </Typography>
                  {summaryMetrics ? <MetricSections value={summaryMetrics} /> : <Alert severity="info">No summary metrics are available yet.</Alert>}
                </Stack>
              </CardContent>
            </Card>
            {detail.targets.length > 0 ? (
              <Stack spacing={2}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Per-target metrics
                </Typography>
                {renderTargetSummary(detail.targets)}
              </Stack>
            ) : (
              <Alert severity="info">No targets are registered yet.</Alert>
            )}
          </Stack>
        )}

        {mainTab === 'feature-importance' && (
          <Stack spacing={2}>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Feature importance
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    Importance is loaded from the persisted model artifact written at training time.
                  </Typography>
                  <FeatureImportanceTab
                    target={detail.feature_importance ?? null}
                    targets={detail.targets.map((target) => target.feature_importance).filter(Boolean) as NonNullable<
                      typeof detail.targets[number]['feature_importance']
                    >[]}
                  />
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        )}

        {mainTab === 'charts' && (
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1fr) 360px' } }}>
            <Stack spacing={2} sx={{ minWidth: 0 }}>
              <Card variant="outlined">
                <CardContent>
                  <Stack spacing={1.5}>
                    <Stack
                      direction={{ xs: 'column', md: 'row' }}
                      spacing={1.5}
                      sx={{ alignItems: { md: 'end' }, justifyContent: 'space-between' }}
                    >
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                          Daily chart
                        </Typography>
                        <Typography color="text.secondary" variant="body2">
                          Pick a holdout day to inspect the intraday candles, model prediction, and walk-forward split.
                        </Typography>
                      </Stack>
                      <TextField
                        select
                        label="Holdout date"
                        value={chartDate}
                        onChange={(event) => setChartDate(event.target.value)}
                        disabled={holdoutDates.length === 0}
                        helperText={
                          holdoutDates.length > 0
                            ? 'Choose from the final holdout sessions only.'
                            : 'No holdout sessions are available for charting yet.'
                        }
                        sx={{ minWidth: 220, maxWidth: 280 }}
                      >
                        {holdoutDates.length === 0 ? (
                          <MenuItem value="" disabled>
                            No holdout dates available
                          </MenuItem>
                        ) : (
                          holdoutDates.map((date) => (
                            <MenuItem key={date} value={date}>
                              {formatHoldoutDate(date)}
                            </MenuItem>
                          ))
                        )}
                      </TextField>
                    </Stack>
                    {holdoutDates.length === 0 && (
                      <Alert severity="info">This forecast does not have holdout chart dates available yet.</Alert>
                    )}
                    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                      <Chip size="small" label={`Resolution ${formatResolution(chartData?.resolution ?? resolution)}`} variant="outlined" />
                      <Chip
                        size="small"
                        label={chartData?.split_label ?? '—'}
                        color={splitLabelColor(chartData?.split_label ?? 'other')}
                        variant="outlined"
                      />
                      <Chip
                        size="small"
                        label={chartData?.source === 'computed' ? 'computed on demand' : 'stored data'}
                        variant="outlined"
                      />
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
              {chartErrorAlert && <Alert severity={chartErrorAlert.severity}>{chartErrorAlert.message}</Alert>}
              <Paper variant="outlined" sx={{ minHeight: 520, p: 1 }}>
                {chartLoading && (
                  <Stack sx={{ alignItems: 'center', justifyContent: 'center', minHeight: 480 }}>
                    <CircularProgress />
                  </Stack>
                )}
                {!chartLoading && chartData && (
                  <CandlestickChart
                    data={chartData.bars}
                    annotationMarkers={chartAnnotationMarkers}
                  />
                )}
                {!chartLoading && !chartData && !chartError && (
                  <Stack sx={{ alignItems: 'center', justifyContent: 'center', minHeight: 480, p: 2 }}>
                    <Typography color="text.secondary">Choose a date to load the chart.</Typography>
                  </Stack>
                )}
              </Paper>
            </Stack>

            <Card variant="outlined" sx={{ alignSelf: 'start', position: { xl: 'sticky' }, top: { xl: 24 } }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack spacing={0.5}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                      Predictions vs labels
                    </Typography>
                    <Typography color="text.secondary" variant="body2">
                      Model output for the selected holdout day with the true target label values alongside it.
                    </Typography>
                  </Stack>
                  {chartData ? (
                    <>
                      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                        <Chip size="small" label={formatHoldoutDate(chartData.selected_date)} variant="outlined" />
                        <Chip size="small" label={splitLabelText(chartData.split_label)} color={splitLabelColor(chartData.split_label)} variant="outlined" />
                        <Chip size="small" label={`${chartPredictions.length} predictions`} variant="outlined" />
                      </Stack>
                      {chartPredictions.length === 0 ? (
                        <Alert severity="info">No prediction rows were returned for this day.</Alert>
                      ) : (
                        <TableContainer component={Paper} variant="outlined">
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell sx={{ fontWeight: 700 }}>Time</TableCell>
                                <TableCell sx={{ fontWeight: 700 }}>Prediction</TableCell>
                                <TableCell sx={{ fontWeight: 700 }}>Label</TableCell>
                                <TableCell sx={{ fontWeight: 700 }}>Delta</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {chartPredictions.map((prediction) => (
                                <TableRow key={`${prediction.session_date}-${prediction.decision_timestamp}-${prediction.decision_time}`} hover>
                                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                    <Stack spacing={0.25}>
                                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                        {prediction.decision_time}
                                      </Typography>
                                      <Chip
                                        size="small"
                                        label={splitLabelText(prediction.split_label)}
                                        color={splitLabelColor(prediction.split_label)}
                                        variant="outlined"
                                      />
                                    </Stack>
                                  </TableCell>
                                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                      {formatSignedBps(prediction.predicted_bps)}
                                    </Typography>
                                  </TableCell>
                                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                    <Stack spacing={0.25}>
                                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                        {formatSignedBps(prediction.actual_bps)}
                                      </Typography>
                                      {prediction.actual_after_cost !== null && prediction.actual_after_cost !== undefined && (
                                        <Typography variant="caption" color="text.secondary">
                                          After cost: {prediction.actual_after_cost ? 'yes' : 'no'}
                                        </Typography>
                                      )}
                                    </Stack>
                                  </TableCell>
                                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                    <Typography
                                      variant="body2"
                                      sx={{
                                        fontWeight: 600,
                                        color:
                                          prediction.delta_bps === null
                                            ? 'text.secondary'
                                            : prediction.delta_bps >= 0
                                              ? 'success.main'
                                              : 'error.main',
                                      }}
                                    >
                                      {formatSignedBps(prediction.delta_bps)}
                                    </Typography>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      )}
                    </>
                  ) : (
                    <Alert severity="info">Load a holdout day to compare the model predictions with the true labels.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Box>
        )}

        {mainTab === 'debug' && (
          <Stack spacing={2}>
            <Alert severity="info">
              Raw JSON payloads live here so the detailed views stay readable.
            </Alert>
            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Operational metadata
                  </Typography>
                  <InfoTable
                    rows={[
                      { label: 'Namespace', value: detail.argo_namespace ?? '—' },
                      { label: 'Workflow', value: detail.argo_workflow_name ?? '—' },
                      { label: 'Feature run id', value: detail.feature_run_id, mono: true },
                      { label: 'Artifact dir', value: detail.artifact_dir, mono: true },
                      { label: 'Status', value: detail.status },
                    ]}
                  />
                </Stack>
              </CardContent>
            </Card>
            <Box component="pre" sx={{ m: 0, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.default', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {JSON.stringify(detail.params, null, 2)}
            </Box>
            <Box component="pre" sx={{ m: 0, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.default', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {JSON.stringify(summaryMetrics ?? {}, null, 2)}
            </Box>
          </Stack>
        )}
      </Stack>

      <Stack spacing={2} sx={{ minWidth: 0, position: { xl: 'sticky' }, top: { xl: 24 }, alignSelf: 'start' }}>
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.5}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Status panel
              </Typography>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
              </Stack>
              {isActive && (
                <Stack spacing={0.75}>
                  <LinearProgress
                    variant="determinate"
                    value={Math.max(0, Math.min(100, progressPct))}
                    sx={{
                      height: 10,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      '& .MuiLinearProgress-bar': {
                        borderRadius: 1,
                      },
                    }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    {Math.round(Math.max(0, Math.min(100, progressPct)))}% complete
                  </Typography>
                </Stack>
              )}
              <Typography variant="body2" color="text.secondary">
                {isActive ? 'This forecast is still updating.' : 'This forecast has reached a terminal state.'}
              </Typography>
              <Divider />
              <Stack spacing={1}>
                {detail.argo_workflow_name && (
                  <Button variant="outlined" startIcon={<BugReportOutlinedIcon />} onClick={() => setWorkflowStepsOpen(true)}>
                    View workflow steps
                  </Button>
                )}
                <Button variant="outlined" startIcon={<BugReportOutlinedIcon />} onClick={() => setWorkflowErrorsOpen(true)}>
                  View workflow errors
                </Button>
                <Button
                  variant="outlined"
                  color="warning"
                  startIcon={<ReplayIcon />}
                  onClick={() => setRetryDialogOpen(true)}
                >
                  Retry model
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.25}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Quick facts
              </Typography>
              <InfoTable
                rows={[
                  { label: 'Symbol', value: featureRun?.symbol ?? '—' },
                  { label: 'Benchmark', value: featureRun?.benchmark_symbol ?? '—' },
                  { label: 'Resolution', value: formatResolution(resolution), mono: true },
                  { label: 'Window', value: detail.feature_run?.manifest ? `${detail.feature_run.manifest.start_date} to ${detail.feature_run.manifest.end_date}` : '—' },
                  { label: 'Targets', value: String(detail.targets.length) },
                ]}
              />
            </Stack>
          </CardContent>
        </Card>
      </Stack>

      <Dialog open={renameDialogOpen} onClose={() => !savingName && setRenameDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Rename forecast</DialogTitle>
        <DialogContent>
          <TextField fullWidth autoFocus label="Name" value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} helperText="Leave blank to clear the name." />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenameDialogOpen(false)} disabled={savingName}>Cancel</Button>
          <Button variant="contained" onClick={() => void saveName()} disabled={savingName}>Save</Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteDialogOpen}
        title={`Delete Daily Index Forecast ${detail.name ?? detail.group_id}?`}
        intent="error"
        icon={<DeleteOutlineIcon />}
        confirmLabel="Delete forecast"
        cancelLabel="Cancel"
        onCancel={() => {
          if (!deleting) {
            setDeleteDialogOpen(false)
          }
        }}
        onConfirm={() => void handleDelete()}
        loading={deleting}
        description={
          <Typography color="text.secondary">
            This permanently deletes the forecast group, its feature extraction run, and their artifact directories.
            If it is running, its Argo workflow will be terminated best-effort.
          </Typography>
        }
      />

      <ConfirmDialog
        open={retryDialogOpen}
        title="Retry Daily Index Forecast?"
        intent="warning"
        icon={<ReplayIcon />}
        confirmLabel="Retry"
        cancelLabel="Cancel"
        onCancel={() => setRetryDialogOpen(false)}
        onConfirm={() => void handleRetry()}
        loading={retrying}
        description={
          <Stack spacing={1}>
            <Typography color="text.secondary">
              This will submit a new Argo workflow using the stored launch parameters for this forecast.
            </Typography>
            <Typography color="text.secondary">
              If Argo rejects the request, the error will be shown here instead of silently disappearing.
            </Typography>
          </Stack>
        }
      />

      <ModelWorkflowErrorDialog
        groupId={workflowErrorsOpen ? detail.group_id : null}
        open={workflowErrorsOpen}
        onClose={() => setWorkflowErrorsOpen(false)}
        entityKind="Daily Index Forecast"
        entityLabel={detailDisplayLabel}
        fetchWorkflowErrors={fetchModelWorkflowErrors as unknown as (groupId: string) => Promise<ModelWorkflowErrorResponse>}
      />

      <WorkflowStepsDialog
        open={workflowStepsOpen}
        onClose={() => setWorkflowStepsOpen(false)}
        entityKind="Daily Index Forecast"
        entityLabel={detailDisplayLabel}
        workflowName={detail.argo_workflow_name ?? ''}
        namespace={detail.argo_namespace ?? null}
        workflowTitle={detail.name ? `${detail.name} (${detail.group_id})` : detail.group_id}
      />
    </Box>
  )
}

export function DailyIndexForecastModelWizardPage({
  createModel,
  dailyIndexDatasetSource = null,
  dailyIndexDatasetId = null,
}: {
  createModel: (payload: DailyIndexForecastCreateRequest) => Promise<{ group_id: string; feature_run_id: string }>
  dailyIndexDatasetSource?: { symbol: string; start_date: string; end_date: string } | null
  dailyIndexDatasetId?: string | null
}) {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [launchMode, setLaunchMode] = useState<'manual' | 'dataset'>(dailyIndexDatasetId ? 'dataset' : 'manual')
  const [manualSymbol, setManualSymbol] = useState(dailyIndexDatasetSource?.symbol ?? 'SPY')
  const [datasetSymbol, setDatasetSymbol] = useState(dailyIndexDatasetSource?.symbol ?? '')
  const [benchmarkSymbol, setBenchmarkSymbol] = useState('QQQ')
  const [name, setName] = useState('')
  const [startDate, setStartDate] = useState(dailyIndexDatasetSource?.start_date ?? '2024-01-01')
  const [endDate, setEndDate] = useState(dailyIndexDatasetSource?.end_date ?? '2024-12-31')
  const [decisionTimes, setDecisionTimes] = useState('09:45')
  const [sourceType, setSourceType] = useState<'alpaca' | 'yahoo' | 'csv'>('alpaca')
  const [interval, setInterval] = useState('5m')
  const [feed, setFeed] = useState('iex')
  const [csvPath, setCsvPath] = useState('')
  const [benchmarkSourceType, setBenchmarkSourceType] = useState<'alpaca' | 'yahoo' | 'csv'>('alpaca')
  const [benchmarkInterval, setBenchmarkInterval] = useState('5m')
  const [benchmarkFeed, setBenchmarkFeed] = useState('iex')
  const [benchmarkCsvPath, setBenchmarkCsvPath] = useState('')
  const [openingWindowMinutes, setOpeningWindowMinutes] = useState(15)
  const [rollingSessions, setRollingSessions] = useState('5,20')
  const [benchmarkSessions, setBenchmarkSessions] = useState('5,20')
  const [useCalendarFeatures, setUseCalendarFeatures] = useState(true)
  const [useCrossMarketFeatures, setUseCrossMarketFeatures] = useState(true)
  const [trainDays, setTrainDays] = useState(90)
  const [validationDays, setValidationDays] = useState(10)
  const [testDays, setTestDays] = useState(10)
  const [stepDays, setStepDays] = useState(10)
  const [embargoDays, setEmbargoDays] = useState(1)
  const [holdoutDays, setHoldoutDays] = useState(20)
  const [alphaGrid, setAlphaGrid] = useState('0.25,1,4,16')
  const [spreadBps, setSpreadBps] = useState(1.5)
  const [slippageBps, setSlippageBps] = useState(1.0)
  const [impactBps, setImpactBps] = useState(0.5)
  const [datasets, setDatasets] = useState<DatasetListItem[]>([])
  const [selectedDatasetDetail, setSelectedDatasetDetail] = useState<DatasetDetailResponse | null>(null)
  const [loadingDatasets, setLoadingDatasets] = useState(false)
  const [datasetsError, setDatasetsError] = useState<string | null>(null)
  const [loadingDatasetDetail, setLoadingDatasetDetail] = useState(false)
  const [datasetDetailError, setDatasetDetailError] = useState<string | null>(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(dailyIndexDatasetId)
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    setLaunchMode(dailyIndexDatasetId ? 'dataset' : 'manual')
    setSelectedDatasetId(dailyIndexDatasetId)
  }, [dailyIndexDatasetId])

  useEffect(() => {
    setManualSymbol(dailyIndexDatasetSource?.symbol ?? 'SPY')
    setDatasetSymbol(dailyIndexDatasetSource?.symbol ?? '')
    setStartDate(dailyIndexDatasetSource?.start_date ?? '2024-01-01')
    setEndDate(dailyIndexDatasetSource?.end_date ?? '2024-12-31')
  }, [dailyIndexDatasetSource])

  useEffect(() => {
    let cancelled = false
    setLoadingDatasets(true)
    fetchDatasets()
      .then((response) => {
        if (cancelled) return
        setDatasets((response.items ?? []).filter((item) => item.status === 'completed'))
      })
      .catch((err) => {
        if (cancelled) return
        setDatasetsError(err instanceof Error ? err.message : 'Failed to load datasets')
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingDatasets(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedDatasetSymbol = useMemo(() => {
    const selected = datasets.find((item) => item.id === selectedDatasetId)
    return selected?.symbol?.trim().toUpperCase() ?? dailyIndexDatasetSource?.symbol?.trim().toUpperCase() ?? ''
  }, [datasets, dailyIndexDatasetSource?.symbol, selectedDatasetId])

  useEffect(() => {
    let cancelled = false
    if (!selectedDatasetId) {
      setSelectedDatasetDetail(null)
      setDatasetDetailError(null)
      setLoadingDatasetDetail(false)
      return () => {
        cancelled = true
      }
    }

    setLoadingDatasetDetail(true)
    setDatasetDetailError(null)
    fetchDatasetDetail(selectedDatasetId)
      .then((response) => {
        if (cancelled) return
        setSelectedDatasetDetail(response)
        const options = response.symbol_options ?? []
        if (options.length > 0) {
          setDatasetSymbol((current) => {
            const preferred = selectedDatasetSymbol
            if (preferred && options.includes(preferred)) return preferred
            if (current && options.includes(current)) return current
            return options[0]
          })
        }
      })
      .catch((err) => {
        if (cancelled) return
        setDatasetDetailError(err instanceof Error ? err.message : 'Failed to load dataset details')
        setSelectedDatasetDetail(null)
      })
      .finally(() => {
        if (!cancelled) setLoadingDatasetDetail(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedDatasetId, selectedDatasetSymbol])

  const datasetSymbolOptions = useMemo(() => {
    const options = selectedDatasetDetail?.symbol_options ?? []
    const preferred = selectedDatasetSymbol
    if (options.length > 0) {
      return options
    }
    return preferred ? [preferred] : []
  }, [selectedDatasetDetail?.symbol_options, selectedDatasetSymbol])

  useEffect(() => {
    if (launchMode !== 'dataset' || datasetSymbolOptions.length === 0) {
      return
    }
    setDatasetSymbol((current) => {
      if (current && datasetSymbolOptions.includes(current)) {
        return current
      }
      const preferred = selectedDatasetSymbol
      if (preferred && datasetSymbolOptions.includes(preferred)) {
        return preferred
      }
      return datasetSymbolOptions[0]
    })
  }, [datasetSymbolOptions, launchMode, selectedDatasetSymbol])

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  )

  async function handleSubmit() {
    if (launchMode === 'dataset') {
      if (loadingDatasets) {
        setValidationError('Loading completed datasets. Please wait and try again.')
        return
      }
      if (datasetsError) {
        setValidationError(datasetsError)
        return
      }
      if (!datasets.length) {
        setValidationError('No completed datasets are available yet.')
        return
      }
      if (!selectedDataset) {
        setValidationError('Select a completed dataset to continue.')
        return
      }
      if (loadingDatasetDetail) {
        setValidationError('Loading symbol options for the selected dataset. Please wait.')
        return
      }
      if (datasetSymbolOptions.length === 0) {
        setValidationError('No symbol could be resolved from the selected dataset.')
        return
      }
    }
    setSubmitting(true)
    try {
      const sourceDataset = launchMode === 'dataset' ? selectedDataset : null
      const selectedSymbol = launchMode === 'dataset' ? datasetSymbol : manualSymbol
      const normalizedSymbol = selectedSymbol.trim().toUpperCase()
      const resolvedSymbol = normalizedSymbol || sourceDataset?.symbol || 'SPY'
      const resolvedBenchmarkSymbol =
        launchMode === 'dataset' ? resolvedSymbol : benchmarkSymbol.trim().toUpperCase()
      const payload: DailyIndexForecastCreateRequest = {
        name: strip(name) || null,
        universe: {
          start_date: sourceDataset?.start_date ?? startDate,
          end_date: sourceDataset?.end_date ?? endDate,
          decision_times: parseCommaList(decisionTimes),
          symbols: [
            {
              symbol: resolvedSymbol,
              data: buildSourceSpec(resolvedSymbol, sourceType, interval, feed, csvPath),
            },
          ],
          benchmark: resolvedBenchmarkSymbol
            ? {
                symbol: resolvedBenchmarkSymbol,
                data: buildSourceSpec(
                  resolvedBenchmarkSymbol,
                  launchMode === 'dataset' ? sourceType : benchmarkSourceType,
                  launchMode === 'dataset' ? interval : benchmarkInterval,
                  launchMode === 'dataset' ? feed : benchmarkFeed,
                  launchMode === 'dataset' ? csvPath : benchmarkCsvPath,
                ),
              }
            : null,
        },
        feature_config: {
          opening_window_minutes: openingWindowMinutes,
          rolling_sessions: parseCommaList(rollingSessions).map((item) => Number(item)).filter((item) => Number.isFinite(item)),
          benchmark_sessions: parseCommaList(benchmarkSessions).map((item) => Number(item)).filter((item) => Number.isFinite(item)),
          use_calendar_features: useCalendarFeatures,
          use_cross_market_features: useCrossMarketFeatures,
        },
        walk_forward: {
          train_days: trainDays,
          validation_days: validationDays,
          test_days: testDays,
          step_days: stepDays,
          embargo_days: embargoDays,
          holdout_days: holdoutDays,
          min_train_rows: 60,
          min_validation_rows: 10,
          min_test_rows: 10,
          min_holdout_rows: 10,
        },
        train_config: {
          alpha_grid: parseCommaList(alphaGrid).map((item) => Number(item)).filter((item) => Number.isFinite(item)),
          residual_distribution: 'normal',
          random_seed: 7,
        },
        costs: {
          spread_bps: spreadBps,
          slippage_bps: slippageBps,
          impact_bps: impactBps,
        },
        data_cache: {},
      }
      const response = await createModel(payload)
      navigate('/models/daily-index', {
        state: {
          launchResult: {
            status: 'success',
            message: 'Daily Index Forecast launch submitted successfully.',
            groupId: response.group_id,
            featureRunId: response.feature_run_id,
          },
        },
      })
    } catch (err) {
      navigate('/models/daily-index', {
        state: {
          launchResult: {
            status: 'failed',
            message: err instanceof Error ? err.message : 'Failed to create Daily Index Forecast',
          },
        },
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography variant="h4" component="h1">
          Launch Daily Index Forecast
        </Typography>
        <Typography color="text.secondary">
          Configure the symbol, decision times, feature extraction, and walk-forward settings for a research run.
        </Typography>
      </Stack>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Universe
              </Typography>
              <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
              {validationError && <Alert severity="warning">{validationError}</Alert>}
              <FormControlLabel
                control={
                  <Switch
                    checked={launchMode === 'dataset'}
                    onChange={(_event, checked) => {
                      setLaunchMode(checked ? 'dataset' : 'manual')
                      setValidationError(null)
                    }}
                  />
                }
                label="Use existing dataset"
              />
              <Typography variant="body2" color="text.secondary">
                Choose a completed dataset to inherit its stored symbol and date range, or keep manual inputs.
              </Typography>
              {launchMode === 'dataset' ? (
                <Stack spacing={1.5}>
                  <Autocomplete
                    options={datasets}
                    value={selectedDataset}
                    isOptionEqualToValue={(option, value) => option.id === value.id}
                    getOptionLabel={(option) => datasetLabel(option)}
                    onChange={(_event, value) => {
                      setSelectedDatasetId(value?.id ?? null)
                      setValidationError(null)
                    }}
                    loading={loadingDatasets}
                    noOptionsText={loadingDatasets ? 'Loading datasets…' : 'No completed datasets are available yet.'}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Existing dataset"
                        placeholder="Search completed datasets"
                        helperText="Search by name, symbol, or date range."
                      />
                    )}
                  />
                  <FormControl fullWidth size="small" disabled={loadingDatasetDetail || datasetSymbolOptions.length === 0}>
                    <InputLabel id="daily-index-dataset-symbol-label">Symbol</InputLabel>
                    <Select
                      labelId="daily-index-dataset-symbol-label"
                      label="Symbol"
                      value={datasetSymbolOptions.includes(datasetSymbol) ? datasetSymbol : datasetSymbolOptions[0] ?? ''}
                      onChange={(event) => setDatasetSymbol(event.target.value as string)}
                    >
                      {datasetSymbolOptions.map((option) => (
                        <MenuItem key={option} value={option}>
                          {option}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {datasetsError && <Alert severity="error">{datasetsError}</Alert>}
                  {loadingDatasets && <Alert severity="info">Loading completed datasets…</Alert>}
                  {!loadingDatasets && !datasetsError && datasets.length === 0 && (
                    <Alert severity="info">
                      No completed datasets are available yet. Launch a dataset job first, then return here.
                    </Alert>
                  )}
                  {datasetDetailError && <Alert severity="warning">{datasetDetailError}</Alert>}
                  {loadingDatasetDetail && <Alert severity="info">Loading symbol options for the selected dataset…</Alert>}
                  {!loadingDatasetDetail && dailyIndexDatasetSource && datasetSymbolOptions.length === 0 && (
                    <Alert severity="warning">No symbol could be resolved from the selected dataset.</Alert>
                  )}
                  {selectedDataset ? (
                    <Stack spacing={1}>
                      <Alert severity="info">
                        Using {selectedDataset.name?.trim() || selectedDataset.symbol} from {selectedDataset.start_date} to {selectedDataset.end_date}.
                      </Alert>
                      <Typography variant="body2" color="text.secondary">
                        The benchmark is locked to the selected dataset symbol.
                      </Typography>
                    </Stack>
                  ) : (
                    !loadingDatasets &&
                    !datasetsError &&
                    datasets.length > 0 && (
                      <Alert severity="warning">
                        Select a completed dataset to inherit its stored provenance.
                      </Alert>
                    )
                  )}
                </Stack>
              ) : (
                <Stack spacing={1.5}>
                  <TextField label="Symbol" value={manualSymbol} onChange={(event) => setManualSymbol(event.target.value.toUpperCase())} />
                  <Stack direction="row" spacing={1}>
                    <TextField fullWidth type="date" label="Start date" value={startDate} onChange={(event) => setStartDate(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
                    <TextField fullWidth type="date" label="End date" value={endDate} onChange={(event) => setEndDate(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
                  </Stack>
                </Stack>
              )}
              <Divider />
              <Stack spacing={1.5}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                  Source configuration
                </Typography>
                <TextField label="Decision times" value={decisionTimes} onChange={(event) => setDecisionTimes(event.target.value)} helperText="Comma-separated, e.g. 09:45,10:15" />
                <FormControl fullWidth>
                  <InputLabel>Data source</InputLabel>
                  <Select value={sourceType} label="Data source" onChange={(event) => setSourceType(event.target.value as 'alpaca' | 'yahoo' | 'csv')}>
                    <MenuItem value="alpaca">Alpaca</MenuItem>
                    <MenuItem value="yahoo">Yahoo</MenuItem>
                    <MenuItem value="csv">CSV</MenuItem>
                  </Select>
                </FormControl>
                <TextField label="Interval" value={interval} onChange={(event) => setInterval(event.target.value)} />
                <TextField label="Feed" value={feed} onChange={(event) => setFeed(event.target.value)} />
                {sourceType === 'csv' && <TextField label="CSV path" value={csvPath} onChange={(event) => setCsvPath(event.target.value)} />}
                {launchMode === 'manual' && (
                  <>
                    <Divider />
                    <TextField
                      label="Benchmark symbol"
                      value={benchmarkSymbol}
                      onChange={(event) => setBenchmarkSymbol(event.target.value.toUpperCase())}
                    />
                    <FormControl fullWidth>
                      <InputLabel>Benchmark source</InputLabel>
                      <Select
                        value={benchmarkSourceType}
                        label="Benchmark source"
                        onChange={(event) => setBenchmarkSourceType(event.target.value as 'alpaca' | 'yahoo' | 'csv')}
                      >
                        <MenuItem value="alpaca">Alpaca</MenuItem>
                        <MenuItem value="yahoo">Yahoo</MenuItem>
                        <MenuItem value="csv">CSV</MenuItem>
                      </Select>
                    </FormControl>
                    <TextField
                      label="Benchmark interval"
                      value={benchmarkInterval}
                      onChange={(event) => setBenchmarkInterval(event.target.value)}
                    />
                    <TextField
                      label="Benchmark feed"
                      value={benchmarkFeed}
                      onChange={(event) => setBenchmarkFeed(event.target.value)}
                    />
                    {benchmarkSourceType === 'csv' && (
                      <TextField
                        label="Benchmark CSV path"
                        value={benchmarkCsvPath}
                        onChange={(event) => setBenchmarkCsvPath(event.target.value)}
                      />
                    )}
                  </>
                )}
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        <Card variant="outlined">
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Feature, walk-forward, and cost settings
              </Typography>
              <TextField type="number" label="Opening window minutes" value={openingWindowMinutes} onChange={(event) => setOpeningWindowMinutes(Number(event.target.value))} />
              <TextField label="Rolling sessions" value={rollingSessions} onChange={(event) => setRollingSessions(event.target.value)} helperText="Comma-separated window sizes" />
              <TextField label="Benchmark sessions" value={benchmarkSessions} onChange={(event) => setBenchmarkSessions(event.target.value)} helperText="Comma-separated window sizes" />
              <FormControlLabel control={<Switch checked={useCalendarFeatures} onChange={(event) => setUseCalendarFeatures(event.target.checked)} />} label="Use calendar features" />
              <FormControlLabel control={<Switch checked={useCrossMarketFeatures} onChange={(event) => setUseCrossMarketFeatures(event.target.checked)} />} label="Use cross-market features" />
              <Divider />
              <Stack direction="row" spacing={1}>
                <TextField fullWidth type="number" label="Train days" value={trainDays} onChange={(event) => setTrainDays(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Validation days" value={validationDays} onChange={(event) => setValidationDays(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Test days" value={testDays} onChange={(event) => setTestDays(Number(event.target.value))} />
              </Stack>
              <Stack direction="row" spacing={1}>
                <TextField fullWidth type="number" label="Step days" value={stepDays} onChange={(event) => setStepDays(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Embargo days" value={embargoDays} onChange={(event) => setEmbargoDays(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Holdout days" value={holdoutDays} onChange={(event) => setHoldoutDays(Number(event.target.value))} />
              </Stack>
              <TextField label="Alpha grid" value={alphaGrid} onChange={(event) => setAlphaGrid(event.target.value)} helperText="Comma-separated ridge alphas" />
              <Stack direction="row" spacing={1}>
                <TextField fullWidth type="number" label="Spread bps" value={spreadBps} onChange={(event) => setSpreadBps(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Slippage bps" value={slippageBps} onChange={(event) => setSlippageBps(Number(event.target.value))} />
                <TextField fullWidth type="number" label="Impact bps" value={impactBps} onChange={(event) => setImpactBps(Number(event.target.value))} />
              </Stack>
            </Stack>
          </CardContent>
          <CardActions sx={{ px: 2, pb: 2, justifyContent: 'flex-start' }}>
            <Button
              data-testid="daily-index-launch-forecast"
              variant="contained"
              onClick={() => void handleSubmit()}
              disabled={submitting}
            >
              Launch forecast
            </Button>
          </CardActions>
        </Card>
      </Box>
    </Stack>
  )
}
