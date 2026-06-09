import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import LaunchIcon from '@mui/icons-material/Launch'
import ReplayIcon from '@mui/icons-material/Replay'
import SearchIcon from '@mui/icons-material/Search'
import {
  Alert,
  Box,
  Checkbox,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  LinearProgress,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableContainer,
} from '@mui/material'
import { useEffect, useMemo, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Link as RouterLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { deleteDailyIndexForecastModel, fetchDailyIndexForecastModelStatus, fetchDailyIndexForecastModels, fetchDailyIndexForecastModelWorkflowErrors, retryDailyIndexForecastModel } from '../api/dailyIndexForecastModels'
import { deleteRiskModel, fetchRiskModelStatus, fetchRiskModels, fetchRiskModelWorkflowErrors, retryRiskModel } from '../api/riskModels'
import { deleteReturnForecastModel, fetchReturnForecastModelStatus, fetchReturnForecastModels, fetchReturnForecastModelWorkflowErrors, retryReturnForecastModel } from '../api/returnForecastModels'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ModelWorkflowErrorDialog } from '../components/ModelWorkflowErrorDialog'
import { useSettings } from '../settings/useSettings'
import type { ModelStatus } from '../types/modelFamilies'
import { formatInTimezone } from '../utils/datetime'
import { isModelActive, resolveModelStatus, statusChipColor } from '../utils/modelStatus'
import type { DailyIndexForecastListItem } from '../types/dailyIndexForecastModels'
import type { ModelListItem, ModelWorkflowErrorResponse, ModelCreateResponse } from '../types/modelFamilies'
import type { ModelLaunchResultState, ModelWizardFamily } from './modelLaunchRoutes'
import { familyDetailPath, familyLabel, familyListPath, familyListSearchParam, familyWizardPath } from './modelLaunchRoutes'

type FamilyFilter = 'all' | ModelWizardFamily
type StatusFilter = 'all' | ModelStatus

interface UnifiedModelRow {
  family: ModelWizardFamily
  familyLabel: string
  singularLabel: string
  groupId: string
  name: string | null
  status: ModelStatus
  createdAt: string
  updatedAt: string
  progressValue: number | null
  progressLabel: string
  sourceSummary: string
  windowSummary: string
  targetsSummary: string
  searchText: string
  detailPath: string
  retryModel?: (groupId: string) => Promise<ModelCreateResponse>
  deleteModel?: (groupId: string) => Promise<void>
  fetchWorkflowErrors?: (groupId: string) => Promise<ModelWorkflowErrorResponse>
  workflowEntityKind: string
}

const FAMILY_TABS: Array<{ value: FamilyFilter; label: string }> = [
  { value: 'all', label: 'All models' },
  { value: 'risk', label: 'Risk' },
  { value: 'return_forecast', label: 'Returns' },
  { value: 'daily_index_forecast', label: 'Daily Index' },
]

const STATUS_FILTERS: StatusFilter[] = ['all', 'pending', 'running', 'succeeded', 'failed', 'canceled']

function parseFamily(value: string | null): FamilyFilter {
  if (value === 'risk') return 'risk'
  if (value === 'returns') return 'return_forecast'
  if (value === 'daily-index') return 'daily_index_forecast'
  return 'all'
}

function parseStatus(value: string | null): StatusFilter {
  if (value === 'pending' || value === 'running' || value === 'succeeded' || value === 'failed' || value === 'canceled') {
    return value
  }
  return 'all'
}

function formatDateTime(value: string, timezone: string, timeDisplayFormat: '12h' | '24h'): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function normalizeText(value: string): string {
  return value.trim().toLowerCase()
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function buildSearchText(parts: Array<string | null | undefined>): string {
  return parts
    .filter((part): part is string => Boolean(part && part.trim()))
    .map((part) => normalizeText(part))
    .join(' ')
}

function sourceSummaryForModel(item: ModelListItem): string {
  const datasetIds = asStringArray(item.dataset_ids)
  if (datasetIds.length > 0) {
    return `${datasetIds.length} dataset${datasetIds.length === 1 ? '' : 's'}`
  }
  const backtestIds = asStringArray(item.backtest_ids)
  if (backtestIds.length > 0) {
    return `${backtestIds.length} backtest${backtestIds.length === 1 ? '' : 's'}`
  }
  return '—'
}

function windowSummaryForModel(item: ModelListItem): string {
  if (item.training_start_date && item.training_end_date) {
    return item.training_start_date === item.training_end_date
      ? item.training_start_date
      : `${item.training_start_date} to ${item.training_end_date}`
  }
  if (item.training_start_date) {
    return item.training_start_date
  }
  if (item.training_end_date) {
    return item.training_end_date
  }
  return '—'
}

function sourceSummaryForDailyIndex(item: DailyIndexForecastListItem): string {
  const benchmark = item.benchmark_symbol ? ` vs ${item.benchmark_symbol}` : ''
  const decisions = asStringArray(item.decision_times).length > 0 ? asStringArray(item.decision_times).join(', ') : '—'
  return `${item.symbol}${benchmark} · ${decisions}`
}

function windowSummaryForDailyIndex(item: DailyIndexForecastListItem): string {
  return item.start_date === item.end_date ? item.start_date : `${item.start_date} to ${item.end_date}`
}

function targetSummary(targets: string[]): string {
  if (!Array.isArray(targets) || targets.length === 0) {
    return '—'
  }
  return targets.join(', ')
}

function ModelStatusProgressCell({
  status,
  progressValue,
  progressLabel,
}: Pick<UnifiedModelRow, 'status' | 'progressValue' | 'progressLabel'>) {
  if (!isModelActive(status)) {
    return <Chip size="small" label={status} color={statusChipColor(status)} />
  }

  return (
    <Stack spacing={0.5} sx={{ minWidth: 140 }}>
      <LinearProgress
        variant={progressValue !== null ? 'determinate' : 'indeterminate'}
        value={progressValue ?? 0}
        sx={{ height: 8, borderRadius: 999 }}
      />
      {progressValue !== null && (
        <Typography variant="caption" color="text.secondary">
          {progressLabel}
        </Typography>
      )}
    </Stack>
  )
}

async function loadFamilyRows(
  family: ModelWizardFamily,
): Promise<UnifiedModelRow[]> {
  if (family === 'risk') {
    const items = await fetchRiskModels()
    const activeRows = items.filter((item) => isModelActive(item.status))
    const statuses = await Promise.allSettled(activeRows.map((item) => fetchRiskModelStatus(item.group_id)))
    const statusMap = new Map<string, ModelStatus>()
    for (const result of statuses) {
      if (result.status === 'fulfilled') {
        statusMap.set(result.value.group_id, resolveModelStatus(result.value.status, result.value.argo_phase))
      }
    }
    return items.map((item) => mapModelRow('risk', item, statusMap.get(item.group_id) ?? item.status))
  }

  if (family === 'return_forecast') {
    const items = await fetchReturnForecastModels()
    const activeRows = items.filter((item) => isModelActive(item.status))
    const statuses = await Promise.allSettled(activeRows.map((item) => fetchReturnForecastModelStatus(item.group_id)))
    const statusMap = new Map<string, ModelStatus>()
    for (const result of statuses) {
      if (result.status === 'fulfilled') {
        statusMap.set(result.value.group_id, resolveModelStatus(result.value.status, result.value.argo_phase))
      }
    }
    return items.map((item) => mapModelRow('return_forecast', item, statusMap.get(item.group_id) ?? item.status))
  }

  const items = await fetchDailyIndexForecastModels()
  const activeRows = items.filter((item) => isModelActive(item.status))
  const statuses = await Promise.allSettled(activeRows.map((item) => fetchDailyIndexForecastModelStatus(item.group_id)))
  const statusMap = new Map<string, { status: ModelStatus; progressValue: number | null }>()
  for (const result of statuses) {
    if (result.status === 'fulfilled') {
      statusMap.set(result.value.group_id, {
        status: resolveModelStatus(result.value.status, result.value.argo_phase),
        progressValue:
          typeof result.value.progress_pct === 'number' && Number.isFinite(result.value.progress_pct)
            ? Math.max(0, Math.min(100, result.value.progress_pct))
            : null,
      })
    }
  }
  return items.map((item) => {
    const next = statusMap.get(item.group_id)
    return mapDailyIndexRow(item, next?.status ?? item.status, next?.progressValue ?? null)
  })
}

function mapModelRow(
  family: 'risk' | 'return_forecast',
  item: ModelListItem,
  status: ModelStatus,
): UnifiedModelRow {
  const familyLabelValue = family === 'risk' ? 'Risk model' : 'Return forecast model'
  const targets = asStringArray(item.targets)
  const sourceSummary = sourceSummaryForModel(item)
  const windowSummary = windowSummaryForModel(item)
  const targetsSummaryValue = targetSummary(targets)
  const searchText = buildSearchText([
    familyLabelValue,
    item.group_id,
    item.name ?? '',
    sourceSummary,
    windowSummary,
    targetsSummaryValue,
    item.summary_metrics ? JSON.stringify(item.summary_metrics) : '',
    item.artifact_dir,
    item.created_at,
    item.updated_at,
    status,
  ])

  return {
    family,
    familyLabel: familyLabelValue,
    singularLabel: familyLabelValue,
    groupId: item.group_id,
    name: item.name ?? null,
    status,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    progressValue:
      typeof item.targets_total === 'number' && item.targets_total > 0
        ? Math.min(100, Math.max(0, (item.targets_done / item.targets_total) * 100))
        : null,
    progressLabel:
      item.targets_total > 0
        ? `${item.targets_done}/${item.targets_total}`
        : isModelActive(status)
          ? 'Updating'
          : '—',
    sourceSummary,
    windowSummary,
    targetsSummary: targetsSummaryValue,
    searchText,
    detailPath: familyDetailPath(family, item.group_id),
    retryModel: family === 'risk' ? retryRiskModel : retryReturnForecastModel,
    deleteModel: family === 'risk' ? deleteRiskModel : deleteReturnForecastModel,
    fetchWorkflowErrors: family === 'risk' ? fetchRiskModelWorkflowErrors : fetchReturnForecastModelWorkflowErrors,
    workflowEntityKind: familyLabelValue,
  }
}

function mapDailyIndexRow(
  item: DailyIndexForecastListItem,
  status: ModelStatus,
  progressValue: number | null = null,
): UnifiedModelRow {
  const familyLabelValue = 'Daily Index Forecast'
  const targets = asStringArray(item.targets)
  const sourceSummary = sourceSummaryForDailyIndex(item)
  const windowSummary = windowSummaryForDailyIndex(item)
  const targetsSummaryValue = targetSummary(targets)
  const searchText = buildSearchText([
    familyLabelValue,
    item.group_id,
    item.feature_run_id,
    item.name ?? '',
    sourceSummary,
    windowSummary,
    targetsSummaryValue,
    item.summary_metrics ? JSON.stringify(item.summary_metrics) : '',
    item.artifact_dir,
    item.feature_run_artifact_dir,
    item.created_at,
    item.updated_at,
    status,
  ])

  return {
    family: 'daily_index_forecast',
    familyLabel: familyLabelValue,
    singularLabel: familyLabelValue,
    groupId: item.group_id,
    name: item.name ?? null,
    status,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    progressValue: isModelActive(status) ? progressValue : null,
    progressLabel: isModelActive(status) && progressValue !== null ? `${Math.round(progressValue)}% complete` : 'Updating',
    sourceSummary,
    windowSummary,
    targetsSummary: targetsSummaryValue,
    searchText,
    detailPath: familyDetailPath('daily_index_forecast', item.group_id),
    retryModel: retryDailyIndexForecastModel,
    deleteModel: deleteDailyIndexForecastModel,
    fetchWorkflowErrors: fetchDailyIndexForecastModelWorkflowErrors,
    workflowEntityKind: familyLabelValue,
  }
}

function launchResultDetailPath(result: ModelLaunchResultState): string {
  return result.groupId ? familyDetailPath(result.family, result.groupId) : familyListPath(result.family)
}

export function ModelsLandingPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { platformSettings, appearance } = useSettings()
  const [searchParams, setSearchParams] = useSearchParams()
  const [rows, setRows] = useState<UnifiedModelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorRow, setWorkflowErrorRow] = useState<UnifiedModelRow | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<UnifiedModelRow | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [retryTarget, setRetryTarget] = useState<UnifiedModelRow | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [launchResult, setLaunchResult] = useState<ModelLaunchResultState | null>(null)
  const [trainMenuAnchorEl, setTrainMenuAnchorEl] = useState<HTMLElement | null>(null)

  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const timezone = platformSettings.platform_behavior.timezone
  const timeDisplayFormat = appearance.time_display_format
  const familyFilter = parseFamily(searchParams.get('family'))
  const statusFilter = parseStatus(searchParams.get('status'))
  const query = normalizeText(searchParams.get('q') ?? '')

  useEffect(() => {
    const state = location.state as { launchResult?: ModelLaunchResultState } | null
    if (!state?.launchResult) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      setLaunchResult(state.launchResult ?? null)
    }, 0)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    navigate(location.pathname + location.search, { replace: true, state: null })
    return () => window.clearTimeout(timeoutId)
  }, [location.pathname, location.search, location.state, navigate])

  useEffect(() => {
    let cancelled = false

    async function loadRows() {
      setLoading(true)
      try {
        const results = await Promise.allSettled([
          loadFamilyRows('risk'),
          loadFamilyRows('return_forecast'),
          loadFamilyRows('daily_index_forecast'),
        ])

        const nextRows: UnifiedModelRow[] = []
        const errors: string[] = []

        for (const result of results) {
          if (result.status === 'fulfilled') {
            nextRows.push(...result.value)
          } else {
            errors.push(result.reason instanceof Error ? result.reason.message : 'Failed to load models')
          }
        }

        nextRows.sort((left, right) => {
          const updatedSort = right.updatedAt.localeCompare(left.updatedAt)
          if (updatedSort !== 0) return updatedSort
          const familySort = left.family.localeCompare(right.family)
          if (familySort !== 0) return familySort
          return left.groupId.localeCompare(right.groupId)
        })

        if (!cancelled) {
          setRows(nextRows)
          setError(errors.length > 0 ? errors.join(' ') : null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load models')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadRows()
    return () => {
      cancelled = true
    }
  }, [])

  const hasActiveRows = useMemo(() => rows.some((row) => isModelActive(row.status)), [rows])

  useEffect(() => {
    if (!hasActiveRows) {
      return undefined
    }

    let cancelled = false

    const tick = async () => {
      try {
        const nextRows = await Promise.all(
          rows.map(async (row) => {
            if (!isModelActive(row.status)) {
              return row
            }

            const nextStatus =
              row.family === 'risk'
                ? await fetchRiskModelStatus(row.groupId)
                : row.family === 'return_forecast'
                  ? await fetchReturnForecastModelStatus(row.groupId)
                  : await fetchDailyIndexForecastModelStatus(row.groupId)
            return {
              ...row,
              status: resolveModelStatus(row.status, nextStatus.argo_phase),
            }
          }),
        )

        if (!cancelled) {
          setRows(
            nextRows.sort((left, right) => {
              const updatedSort = right.updatedAt.localeCompare(left.updatedAt)
              if (updatedSort !== 0) return updatedSort
              const familySort = left.family.localeCompare(right.family)
              if (familySort !== 0) return familySort
              return left.groupId.localeCompare(right.groupId)
            }),
          )
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh models')
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
  }, [hasActiveRows, refreshIntervalMs, rows])

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      if (familyFilter !== 'all' && row.family !== familyFilter) {
        return false
      }
      if (statusFilter !== 'all' && row.status !== statusFilter) {
        return false
      }
      if (query.length > 0 && !row.searchText.includes(query)) {
        return false
      }
      return true
    })
  }, [familyFilter, query, rows, statusFilter])

  const familyCounts = useMemo(
    () =>
      FAMILY_TABS.map((tab) => ({
        ...tab,
        count: tab.value === 'all' ? rows.length : rows.filter((row) => row.family === tab.value).length,
      })),
    [rows],
  )

  const statusCounts = useMemo(
    () =>
      STATUS_FILTERS.map((status) => ({
        status,
        count: status === 'all' ? rows.length : rows.filter((row) => row.status === status).length,
      })),
    [rows],
  )

  const selectedVisibleCount = useMemo(
    () => filteredRows.filter((row) => selectedIds.has(row.groupId)).length,
    [filteredRows, selectedIds],
  )
  const allVisibleSelected = filteredRows.length > 0 && selectedVisibleCount === filteredRows.length
  const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected
  const selectionSummaryLabel =
    filteredRows.length === 0
      ? '0 visible'
      : `${selectedVisibleCount} selected / ${filteredRows.length} visible`

  async function confirmDelete() {
    if (!deleteTarget || !deleteTarget.deleteModel) return
    setDeleting(true)
    setError(null)
    try {
      await deleteTarget.deleteModel(deleteTarget.groupId)
      setDeleteTarget(null)
      setRows((current) => current.filter((row) => row.groupId !== deleteTarget.groupId))
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to delete ${deleteTarget.singularLabel.toLowerCase()}`)
    } finally {
      setDeleting(false)
    }
  }

  async function retryModel() {
    if (!retryTarget || !retryTarget.retryModel) return
    setRetrying(true)
    setError(null)
    try {
      await retryTarget.retryModel(retryTarget.groupId)
      setRetryTarget(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to retry ${retryTarget.singularLabel.toLowerCase()}`)
    } finally {
      setRetrying(false)
    }
  }

  function updateSearchParam(key: string, value: string | null) {
    const next = new URLSearchParams(searchParams)
    if (value === null || value.length === 0) {
      next.delete(key)
    } else {
      next.set(key, value)
    }
    setSearchParams(next, { replace: true })
  }

  const familyTabValue = familyFilter === 'all' ? 'all' : familyListSearchParam(familyFilter)
  const trainMenuOpen = trainMenuAnchorEl !== null

  function toggleRowSelection(groupId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(groupId)
      } else {
        next.delete(groupId)
      }
      return next
    })
  }

  function toggleSelectAllVisible(checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current)
      for (const row of filteredRows) {
        if (checked) {
          next.add(row.groupId)
        } else {
          next.delete(row.groupId)
        }
      }
      return next
    })
  }

  function openTrainWizard(family: ModelWizardFamily) {
    setTrainMenuAnchorEl(null)
    navigate(familyWizardPath(family))
  }

  function handleTrainModelClick(event: ReactMouseEvent<HTMLButtonElement>) {
    if (familyFilter !== 'all') {
      openTrainWizard(familyFilter)
      return
    }
    setTrainMenuAnchorEl(event.currentTarget)
  }

  async function confirmBulkDelete() {
    const ids = filteredRows.filter((row) => selectedIds.has(row.groupId)).map((row) => row.groupId)
    if (ids.length === 0) {
      return
    }

    setBulkDeleting(true)
    setError(null)
    const failedIds: string[] = []

    for (const groupId of ids) {
      const row = rows.find((candidate) => candidate.groupId === groupId)
      if (!row?.deleteModel) {
        failedIds.push(groupId)
        continue
      }

      try {
        await row.deleteModel(groupId)
      } catch {
        failedIds.push(groupId)
      }
    }

    const succeededIds = ids.filter((id) => !failedIds.includes(id))
    setSelectedIds(new Set(failedIds))
    setBulkDeleteOpen(false)
    setRows((current) => current.filter((row) => !succeededIds.includes(row.groupId)))
    setBulkDeleting(false)

    if (failedIds.length > 0) {
      setError(`Deleted ${succeededIds.length} model(s). Failed to delete ${failedIds.length}.`)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.75}>
        <Typography variant="h4" component="h1">
          Models
        </Typography>
        <Typography color="text.secondary" sx={{ maxWidth: 860 }}>
          Browse all trained models in one place, then filter by family, status, or any text that appears in the model
          metadata.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {launchResult && (
        <Dialog
          open
          onClose={() => setLaunchResult(null)}
          aria-labelledby="model-launch-result-title"
          aria-describedby="model-launch-result-description"
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
          <DialogTitle id="model-launch-result-title" sx={{ pb: 1 }}>
            {launchResult.status === 'success' ? `${familyLabel(launchResult.family)} launched` : `${familyLabel(launchResult.family)} launch failed`}
          </DialogTitle>
          <DialogContent id="model-launch-result-description" sx={{ pt: 0 }}>
            <Stack spacing={1.5}>
              <Alert severity={launchResult.status === 'success' ? 'success' : 'error'}>{launchResult.message}</Alert>
              {launchResult.status === 'success' && launchResult.groupId && (
                <Typography color="text.secondary">
                  You can open the new model from{' '}
                  <Button
                    component={RouterLink}
                    to={launchResultDetailPath(launchResult)}
                    sx={{ px: 0.5, minWidth: 'auto', fontWeight: 600, textTransform: 'none' }}
                  >
                    {launchResult.modelName ?? launchResult.groupId}
                  </Button>
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
      )}

      <Paper
        variant="outlined"
        sx={(theme) => ({
          p: { xs: 1.5, md: 2 },
          overflow: 'hidden',
          borderRadius: 4,
          borderColor: theme.palette.divider,
          bgcolor:
            theme.palette.mode === 'dark'
              ? 'rgba(17, 24, 39, 0.62)'
              : 'rgba(255, 255, 255, 0.8)',
          backdropFilter: 'blur(18px)',
          boxShadow:
            theme.palette.mode === 'dark'
              ? '0 20px 50px rgba(15, 23, 42, 0.28)'
              : '0 20px 50px rgba(15, 23, 42, 0.08)',
        })}
      >
        <Stack spacing={1.5}>
          <Box
            sx={{
              display: 'grid',
              gap: 1.5,
              alignItems: 'start',
              gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.6fr) minmax(280px, 1fr)' },
            }}
          >
            <Stack spacing={1.25}>
              <Tabs
                value={familyTabValue}
                onChange={(_, nextValue: string) => updateSearchParam('family', nextValue === 'all' ? null : nextValue)}
                variant="scrollable"
                allowScrollButtonsMobile
                sx={{
                  minHeight: 44,
                  '& .MuiTabs-indicator': {
                    display: 'none',
                  },
                  '& .MuiTabs-flexContainer': {
                    gap: 1,
                  },
                }}
              >
                {familyCounts.map((tab) => (
                  <Tab
                    key={tab.value}
                    value={tab.value === 'all' ? 'all' : familyListSearchParam(tab.value)}
                    label={`${tab.label} (${tab.count})`}
                    sx={{
                      minHeight: 40,
                      minWidth: 'auto',
                      px: 1.5,
                      py: 0.75,
                      borderRadius: 999,
                      border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'background.paper',
                      color: 'text.secondary',
                      textTransform: 'none',
                      fontWeight: 600,
                      '&.Mui-selected': {
                        color: 'primary.main',
                        borderColor: 'primary.main',
                        bgcolor: 'action.selected',
                      },
                    }}
                  />
                ))}
              </Tabs>

              <TextField
                value={searchParams.get('q') ?? ''}
                onChange={(event) => updateSearchParam('q', event.target.value)}
                label="Search models"
                placeholder="Model name, ID, source, or metric"
                size="small"
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon fontSize="small" />
                      </InputAdornment>
                    ),
                  },
                }}
                sx={{
                  maxWidth: 860,
                  '& .MuiOutlinedInput-root': {
                    borderRadius: 999,
                  },
                }}
              />
            </Stack>

            <Stack spacing={1} sx={{ alignItems: { xs: 'stretch', lg: 'flex-end' } }}>
              <Chip
                size="small"
                variant="outlined"
                label={selectionSummaryLabel}
                sx={{
                  alignSelf: { xs: 'flex-start', lg: 'flex-end' },
                  maxWidth: 'fit-content',
                  fontWeight: 600,
                }}
              />
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                sx={{
                  width: '100%',
                  justifyContent: { xs: 'flex-start', lg: 'flex-end' },
                }}
              >
                <Button
                  variant="contained"
                  onClick={handleTrainModelClick}
                  aria-haspopup={familyFilter === 'all' ? 'menu' : undefined}
                  aria-expanded={familyFilter === 'all' ? trainMenuOpen : undefined}
                  sx={{ width: { xs: '100%', sm: 'auto' } }}
                >
                  Train model
                </Button>
                <Button
                  color="error"
                  variant="outlined"
                  disabled={selectedVisibleCount === 0 || bulkDeleting}
                  onClick={() => setBulkDeleteOpen(true)}
                  sx={{ width: { xs: '100%', sm: 'auto' } }}
                >
                  Delete selected{selectedVisibleCount > 0 ? ` (${selectedVisibleCount})` : ''}
                </Button>
              </Stack>
            </Stack>
          </Box>

          <Divider />

          <Box
            sx={{
              display: 'flex',
              gap: 1,
              flexWrap: 'wrap',
              alignItems: 'center',
            }}
          >
            <Typography
              variant="overline"
              sx={{
                letterSpacing: '0.16em',
                color: 'text.secondary',
                lineHeight: 1,
              }}
            >
              Status
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {statusCounts.map(({ status, count }) => (
                <Chip
                  key={status}
                  clickable
                  color={statusFilter === status ? 'primary' : 'default'}
                  variant={statusFilter === status ? 'filled' : 'outlined'}
                  label={status === 'all' ? `All statuses (${count})` : `${status} (${count})`}
                  onClick={() => updateSearchParam('status', status === 'all' ? null : status)}
                  sx={{
                    fontWeight: 600,
                  }}
                />
              ))}
            </Stack>
          </Box>
        </Stack>
      </Paper>

      <Menu
        anchorEl={trainMenuAnchorEl}
        open={trainMenuOpen}
        onClose={() => setTrainMenuAnchorEl(null)}
      >
        <MenuItem onClick={() => openTrainWizard('risk')}>Risk model</MenuItem>
        <MenuItem onClick={() => openTrainWizard('return_forecast')}>Return forecast model</MenuItem>
        <MenuItem onClick={() => openTrainWizard('daily_index_forecast')}>Daily index forecast model</MenuItem>
      </Menu>

      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        {loading ? (
          <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1.5}>
            <CircularProgress />
            <Typography color="text.secondary">Loading models…</Typography>
          </Stack>
        ) : filteredRows.length === 0 ? (
          <Stack sx={{ py: 8, alignItems: 'center', px: 2 }} spacing={1}>
            <Typography variant="h6">No models match your filters</Typography>
            <Typography color="text.secondary" sx={{ textAlign: 'center', maxWidth: 560 }}>
              Try a different family, status, or search term. The unified list includes risk models, return forecasts,
              and Daily Index Forecast runs together.
            </Typography>
          </Stack>
        ) : (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small" stickyHeader aria-label="models table">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={allVisibleSelected}
                      indeterminate={someVisibleSelected}
                      aria-label="Select all models on this page"
                      onChange={(event) => toggleSelectAllVisible(event.target.checked)}
                    />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Family</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Model</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 220 }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Source</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Training window</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Created</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredRows.map((row) => {
                  const rowCreatedAt = formatDateTime(row.createdAt, timezone, timeDisplayFormat)
                  const isSelected = selectedIds.has(row.groupId)
                  return (
                    <TableRow
                      key={`${row.family}-${row.groupId}`}
                      hover
                      selected={isSelected}
                      sx={{ cursor: 'pointer' }}
                      onClick={() => navigate(row.detailPath)}
                    >
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={isSelected}
                          aria-label={`Select model ${row.groupId}`}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => toggleRowSelection(row.groupId, event.target.checked)}
                        />
                      </TableCell>
                      <TableCell>
                        <Chip size="small" variant="outlined" label={row.familyLabel} />
                      </TableCell>
                      <TableCell>
                        <Stack spacing={0.25}>
                          <Typography sx={{ fontWeight: 700 }}>{row.name ?? 'Untitled model'}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            {row.groupId}
                          </Typography>
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ minWidth: 220 }}>
                        <ModelStatusProgressCell
                          status={row.status}
                          progressValue={row.progressValue}
                          progressLabel={row.progressLabel}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{row.sourceSummary}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{row.windowSummary}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{rowCreatedAt}</Typography>
                      </TableCell>
                      <TableCell align="right" onClick={(event) => event.stopPropagation()}>
                        <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                          <Tooltip title="Open details">
                            <IconButton size="small" aria-label="Open details" onClick={() => navigate(row.detailPath)}>
                              <LaunchIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          {row.status === 'failed' && row.fetchWorkflowErrors && (
                            <Tooltip title="Workflow errors">
                              <span>
                                <IconButton
                                  size="small"
                                  color="error"
                                  aria-label="Workflow errors"
                                  onClick={() => setWorkflowErrorRow(row)}
                                >
                                  <BugReportOutlinedIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                          {row.status === 'failed' && row.retryModel && (
                            <Tooltip title="Retry training">
                              <span>
                                <IconButton
                                  size="small"
                                  color="warning"
                                  aria-label="Retry training"
                                  disabled={retrying && retryTarget?.groupId === row.groupId}
                                  onClick={() => setRetryTarget(row)}
                                >
                                  <ReplayIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                          {row.deleteModel && (
                            <Tooltip title="Delete">
                              <span>
                                <IconButton
                                  size="small"
                                  color="error"
                                  aria-label={`Delete ${row.singularLabel.toLowerCase()}`}
                                  disabled={deleting && deleteTarget?.groupId === row.groupId}
                                  onClick={() => setDeleteTarget(row)}
                                >
                                  <DeleteOutlineIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      <ModelWorkflowErrorDialog
        groupId={workflowErrorRow?.groupId ?? null}
        open={workflowErrorRow !== null}
        onClose={() => setWorkflowErrorRow(null)}
        entityKind={workflowErrorRow?.workflowEntityKind ?? 'Model'}
        entityLabel={workflowErrorRow ? `${workflowErrorRow.singularLabel} ${workflowErrorRow.groupId}` : 'Model'}
        fetchWorkflowErrors={
          workflowErrorRow?.fetchWorkflowErrors ??
          (async () => {
            throw new Error('Workflow errors are unavailable')
          })
        }
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `Delete ${deleteTarget.singularLabel.toLowerCase()} ${deleteTarget.name ?? deleteTarget.groupId}?` : 'Delete model'}
        intent="error"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
        loading={deleting}
        description={
          <Typography color="text.secondary">
            This deletes the model group, its database rows, and its artifact directory. If it is running, its Argo
            workflow will be terminated best-effort.
          </Typography>
        }
      />

      <ConfirmDialog
        open={retryTarget !== null}
        title={retryTarget ? `Retry ${retryTarget.singularLabel.toLowerCase()} ${retryTarget.groupId}?` : 'Retry model'}
        intent="warning"
        confirmLabel="Retry"
        cancelLabel="Cancel"
        onCancel={() => setRetryTarget(null)}
        onConfirm={() => void retryModel()}
        loading={retrying}
        description={
          <Typography color="text.secondary">
            This will submit a new Argo workflow using the stored launch parameters for this model.
          </Typography>
        }
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        title={`Delete ${selectedVisibleCount} model${selectedVisibleCount === 1 ? '' : 's'}?`}
        intent="error"
        confirmLabel={`Delete ${selectedVisibleCount}`}
        cancelLabel="Cancel"
        onCancel={() => {
          if (!bulkDeleting) {
            setBulkDeleteOpen(false)
          }
        }}
        onConfirm={() => void confirmBulkDelete()}
        loading={bulkDeleting}
        description={
          <Typography color="text.secondary">
            This permanently removes the selected model records and their artifact directories. If any are running,
            their Argo workflows will be terminated best-effort.
          </Typography>
        }
      />
    </Stack>
  )
}
