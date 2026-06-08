import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom'

import {
  backtestReportUrl,
  deleteBacktest,
  fetchBacktestDetail,
  fetchBacktestStatus,
  retryBacktest,
  retryBacktestForce,
  updateBacktest,
} from '../api/backtests'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { BacktestProgressPanel } from '../components/BacktestProgressPanel'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
import { BacktestArtifactInventory } from '../components/BacktestArtifactInventory'
import { BacktestArtifactChips, publicArtifacts, sidecarArtifacts } from '../components/BacktestArtifactChips'
import { BacktestCliCommandsSection } from '../components/BacktestCliCommandsSection'
import { BacktestConfigInspector } from '../components/BacktestConfigInspector'
import { BacktestRunDetailPanel } from '../components/BacktestRunDetailPanel'
import { BacktestRunsComparisonTable } from '../components/BacktestRunsComparisonTable'
import { BacktestStrategyAggregatePanel } from '../components/BacktestStrategyAggregatePanel'
import { BacktestSummaryDashboard } from '../components/BacktestSummaryDashboard'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import { useSettings } from '../settings/useSettings'
import type { BacktestDetailResponse, BacktestListItem, BacktestStatusResponse } from '../types/backtests'
import type { ComparisonViewMode } from '../utils/backtestAggregates'
import {
  findRunById,
  findStrategyAggregate,
  resolveReportAggregates,
} from '../utils/backtestAggregates'
import { summarizeCandidateActivity } from '../utils/backtestDiagnostics'
import { formatInTimezone } from '../utils/datetime'
import { canEditAndRetryBacktest, canRetryBacktest } from '../utils/backtestConfigPrefill'
import type { BacktestSelectionSummary } from '../types/backtests'

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function listItemToStatus(item: BacktestListItem): BacktestStatusResponse {
  const progress_pct =
    item.total_runs === 0 ? 0 : Math.min(100, (item.completed_runs / item.total_runs) * 100)
  return {
    ...item,
    progress_pct,
    is_terminal: item.status === 'completed' || item.status === 'failed',
  }
}

function deriveSelectionFromReport(report: BacktestDetailResponse['report']): BacktestSelectionSummary | null {
  const inputConfig = report?.input_config
  if (!inputConfig || typeof inputConfig !== 'object') {
    return null
  }

  const runsValue = (inputConfig as { runs?: unknown }).runs
  if (!Array.isArray(runsValue) || runsValue.length === 0) {
    return null
  }

  const symbols: string[] = []
  const triggers: string[] = []
  const exitRules: string[] = []
  let startDate: string | null = null
  let endDate: string | null = null
  let resolution = '1d'
  let feed: BacktestSelectionSummary['feed'] = 'iex'

  for (const run of runsValue) {
    if (!run || typeof run !== 'object') {
      continue
    }

    const runRecord = run as Record<string, unknown>
    if (startDate === null && typeof runRecord.start_date === 'string') {
      startDate = runRecord.start_date
    }
    if (typeof runRecord.end_date === 'string') {
      endDate = runRecord.end_date
    }

    const data = runRecord.data
    if (data && typeof data === 'object') {
      const dataRecord = data as Record<string, unknown>
      if (typeof dataRecord.symbol === 'string' && !symbols.includes(dataRecord.symbol)) {
        symbols.push(dataRecord.symbol)
      }
      if (typeof dataRecord.interval === 'string') {
        resolution = dataRecord.interval
      }
      if (dataRecord.feed === 'iex' || dataRecord.feed === 'sip' || dataRecord.feed === 'otc') {
        feed = dataRecord.feed
      }
    }

    const trigger = runRecord.trigger
    if (trigger && typeof trigger === 'object') {
      const triggerRecord = trigger as Record<string, unknown>
      if (typeof triggerRecord.name === 'string' && !triggers.includes(triggerRecord.name)) {
        triggers.push(triggerRecord.name)
      }
    }

    const exitRulesValue = runRecord.exit_rules
    if (exitRulesValue && typeof exitRulesValue === 'object' && !Array.isArray(exitRulesValue)) {
      const exitRulesRecord = exitRulesValue as Record<string, unknown>
      if (typeof exitRulesRecord.name === 'string' && !exitRules.includes(exitRulesRecord.name)) {
        exitRules.push(exitRulesRecord.name)
      }
    }
  }

  if (!startDate || !endDate) {
    return null
  }

  return {
    start_date: startDate,
    end_date: endDate,
    resolution,
    feed,
    symbols: symbols.length > 0 ? symbols : ['UNKNOWN'],
    triggers: triggers.length > 0 ? triggers : ['unknown'],
    exit_rules: exitRules.length > 0 ? exitRules : ['unknown'],
  }
}

export function BacktestDetailPage() {
  const { platformSettings, appearance } = useSettings()
  const navigate = useNavigate()
  const location = useLocation()
  const { backtestId = '' } = useParams()
  const retriedFromId =
    (location.state as { retriedFrom?: string } | null)?.retriedFrom ?? null
  const [detail, setDetail] = useState<BacktestDetailResponse | null>(null)
  const [metadata, setMetadata] = useState<BacktestStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ComparisonViewMode>('symbol')
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [symbolsDialogOpen, setSymbolsDialogOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const isActive = metadata?.status === 'pending' || metadata?.status === 'running'

  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchBacktestDetail(backtestId)
        if (!cancelled) {
          setDetail(response)
          setMetadata((current) => current ?? listItemToStatus(response.metadata))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load backtest detail')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [backtestId])

  useEffect(() => {
    setNameDraft((metadata?.name ?? '').toString())
  }, [metadata?.name])

  useEffect(() => {
    if (!backtestId) {
      return undefined
    }

    let cancelled = false
    let timer: ReturnType<typeof window.setInterval> | undefined

    const pollStatus = async (): Promise<boolean> => {
      try {
        const status = await fetchBacktestStatus(backtestId)
        if (cancelled) {
          return true
        }

        setMetadata(status)

        if (status.is_terminal) {
          const nextDetail = await fetchBacktestDetail(backtestId)
          if (!cancelled) {
            setDetail(nextDetail)
            setMetadata(status)
            setLoading(false)
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh backtest status')
        }
        return true
      }
    }

    void (async () => {
      const terminal = await pollStatus()
      if (terminal || cancelled) {
        return
      }

      timer = window.setInterval(() => {
        void pollStatus().then((done) => {
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
  }, [backtestId, refreshIntervalMs])

  const report = detail?.report ?? null
  const resolvedSelection = metadata?.selection ?? deriveSelectionFromReport(report)
  const canRetry = metadata ? canRetryBacktest(metadata) : false
  const canEditAndRetry = metadata ? canEditAndRetryBacktest(metadata, report?.input_config) : false
  const candidateSummary = useMemo(
    () => (report ? summarizeCandidateActivity(report.results) : null),
    [report],
  )
  const resolvedAggregates = useMemo(
    () => (report ? resolveReportAggregates(report) : null),
    [report],
  )

  useEffect(() => {
    if (!report || selectedRowId || viewMode !== 'symbol') {
      return
    }
    const firstRun = report.results.find((result) => result.status === 'success') ?? report.results[0]
    if (firstRun) {
      setSelectedRowId(firstRun.run_id)
    }
  }, [report, selectedRowId, viewMode])

  const selectedRun =
    report && selectedRowId && viewMode === 'symbol'
      ? findRunById(report.results, selectedRowId)
      : undefined
  const selectedStrategyAggregate =
    resolvedAggregates && selectedRowId && viewMode === 'strategy'
      ? findStrategyAggregate(resolvedAggregates.aggregates, selectedRowId)
      : undefined

  async function confirmDelete() {
    if (!metadata) {
      return
    }

    setDeleting(true)
    setError(null)
    try {
      await deleteBacktest(metadata.id)
      navigate('/backtests')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete backtest')
      setDeleteDialogOpen(false)
    } finally {
      setDeleting(false)
    }
  }

  const trimmedNameDraft = nameDraft.trim()
  const normalizedNameDraft = trimmedNameDraft ? trimmedNameDraft : ''
  const normalizedCurrentName = (metadata?.name ?? '').toString()
  const nameDirty = Boolean(metadata) && normalizedNameDraft !== normalizedCurrentName

  async function saveName() {
    if (!backtestId || !nameDirty) {
      return
    }
    setSavingName(true)
    setError(null)
    try {
      const updated = await updateBacktest(backtestId, {
        name: trimmedNameDraft ? trimmedNameDraft : null,
      })
      setMetadata((current) =>
        current ? { ...current, name: updated.name ?? null } : current,
      )
      setDetail((current) =>
        current ? { ...current, metadata: { ...current.metadata, name: updated.name ?? null } } : current,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update backtest name')
    } finally {
      setSavingName(false)
    }
  }

  async function handleRetry() {
    if (!metadata) {
      return
    }

    setRetrying(true)
    setError(null)
    try {
      const isActive = metadata.status === 'pending' || metadata.status === 'running'
      const response = isActive ? await retryBacktestForce(metadata.id) : await retryBacktest(metadata.id)
      navigate(`/backtests/${response.backtest_id}`, {
        state: { retriedFrom: metadata.id },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry backtest')
    } finally {
      setRetrying(false)
      setRetryDialogOpen(false)
    }
  }

  if (loading && !metadata) {
    return (
      <Stack sx={{ py: 10, alignItems: 'center' }} spacing={1}>
        <CircularProgress />
        <Typography color="text.secondary">Loading backtest detail…</Typography>
      </Stack>
    )
  }

  if (error && !metadata) {
    return <Alert severity="error">{error}</Alert>
  }

  if (!metadata) {
    return <Alert severity="warning">Backtest detail is unavailable.</Alert>
  }

  const selectionSymbols = resolvedSelection?.symbols ?? []
  const visibleSymbols = selectionSymbols.slice(0, 30)
  const hiddenSymbolCount = Math.max(0, selectionSymbols.length - visibleSymbols.length)
  const symbolsInline = selectionSymbols.length > 0 ? visibleSymbols.join(', ') : '—'

  return (
    <Stack spacing={3}>
      <Stack spacing={2}>
        <Button component={RouterLink} to="/backtests" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to results
        </Button>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1}
          sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
        >
          <Box>
            <Typography variant="h4">Backtest Analysis</Typography>
            <Typography color="text.secondary">
              Result id `{metadata.id}` created{' '}
              {formatTimestamp(
                metadata.created_at,
                platformSettings.platform_behavior.timezone,
                appearance.time_display_format,
              )}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1, alignItems: { sm: 'center' } }}>
              <TextField
                label="Name"
                size="small"
                value={nameDraft}
                onChange={(event) => setNameDraft(event.target.value)}
                placeholder="(optional)"
                slotProps={{ htmlInput: { maxLength: 256 } }}
                sx={{ minWidth: { xs: '100%', sm: 320 } }}
              />
              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  size="small"
                  disabled={!nameDirty || savingName}
                  onClick={() => {
                    void saveName()
                  }}
                >
                  {savingName ? 'Saving…' : 'Save'}
                </Button>
                <Button
                  variant="text"
                  size="small"
                  disabled={!nameDirty || savingName}
                  onClick={() => setNameDraft(normalizedCurrentName)}
                >
                  Cancel
                </Button>
              </Stack>
            </Stack>
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            {canRetry && (
              <Tooltip
                title={
                  metadata.status === 'pending' || metadata.status === 'running'
                    ? 'Launch a new backtest from the same configuration (does not stop the current run)'
                    : 'Launch a new backtest with the same configuration'
                }
              >
                <span>
                  <Button
                    variant="contained"
                    startIcon={retrying ? <CircularProgress size={18} color="inherit" /> : <ReplayIcon />}
                    disabled={retrying}
                    onClick={() => {
                      setRetryDialogOpen(true)
                    }}
                  >
                    {metadata.status === 'pending' || metadata.status === 'running' ? 'Run again' : 'Retry'}
                  </Button>
                </span>
              </Tooltip>
            )}
            <Tooltip
              title={
                canEditAndRetry
                  ? 'Open the wizard with this backtest configuration'
                  : 'Available once the configuration is available.'
              }
            >
              <span>
                <Button
                  component={RouterLink}
                  to={`/backtests/new?from=${metadata.id}`}
                  variant="outlined"
                  startIcon={<ReplayIcon />}
                  disabled={!canEditAndRetry}
                >
                  Edit and run
                </Button>
              </span>
            </Tooltip>
            <BacktestStatusChip status={metadata.status} />
            {metadata.report_status && <ReportStatusChip status={metadata.report_status} />}
            {metadata.execution_backend === 'argo' && (
              <Chip size="small" label="Argo" color="info" variant="outlined" />
            )}
            <Tooltip title="Delete backtest">
              <span>
                <IconButton
                  aria-label="Delete backtest"
                  disabled={deleting}
                  onClick={() => setDeleteDialogOpen(true)}
                  size="small"
                  sx={{
                    color: 'text.disabled',
                    '&:hover': { color: 'error.main', bgcolor: 'action.hover' },
                  }}
                >
                  {deleting ? <CircularProgress size={18} /> : <DeleteOutlineIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {retriedFromId && (
        <Alert severity="info">
          Retried from{' '}
          <Link component={RouterLink} to={`/backtests/${retriedFromId}`}>
            {retriedFromId}
          </Link>
          .
        </Alert>
      )}

      {metadata.workflow_name && (
        <Alert
          severity="info"
          action={
            <Button size="small" variant="outlined" onClick={() => setWorkflowStepsOpen(true)}>
              View workflow steps
            </Button>
          }
        >
          Argo workflow: {metadata.workflow_name}
          {metadata.workflow_namespace ? ` (${metadata.workflow_namespace})` : ''}
        </Alert>
      )}

      {isActive && metadata && (
        <BacktestProgressPanel
          progressPct={metadata.progress_pct}
          isIndeterminate={metadata.total_runs === 0}
          startedAt={metadata.started_at ?? metadata.created_at}
        />
      )}

      {metadata.error_message && metadata.status === 'failed' && (
        <Alert severity="error">{metadata.error_message}</Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Submission summary</Typography>
          {resolvedSelection ? (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Metric label="Date range" value={`${resolvedSelection.start_date} → ${resolvedSelection.end_date}`} />
              <Metric label="Resolution" value={resolvedSelection.resolution} />
              <Metric
                label="Symbols"
                value={
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                    <Typography>{symbolsInline}</Typography>
                    {hiddenSymbolCount > 0 && (
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => setSymbolsDialogOpen(true)}
                        sx={{ px: 0.5, minWidth: 'auto' }}
                      >
                        +{hiddenSymbolCount} more
                      </Button>
                    )}
                  </Stack>
                }
              />
              <Metric label="Triggers" value={resolvedSelection.triggers.join(', ')} />
              <Metric label="Exit rules" value={resolvedSelection.exit_rules.join(', ')} />
            </Stack>
          ) : (
            <Typography color="text.secondary">Selection summary unavailable.</Typography>
          )}
        </Stack>
      </Paper>

      <Dialog
        open={symbolsDialogOpen}
        onClose={() => setSymbolsDialogOpen(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Symbols ({selectionSymbols.length})</DialogTitle>
        <DialogContent dividers>
          {selectionSymbols.length === 0 ? (
            <Typography color="text.secondary">No symbols available.</Typography>
          ) : (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {selectionSymbols.map((symbol) => (
                <Chip key={symbol} label={symbol} size="small" />
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSymbolsDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <BacktestArtifactInventory
        artifacts={publicArtifacts(detail?.artifacts ?? metadata.stored_artifacts ?? [])}
      />

      {report ? (
        <>
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">Report overview</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                <Metric
                  label="Generated"
                  value={formatTimestamp(
                    report.generated_at,
                    platformSettings.platform_behavior.timezone,
                    appearance.time_display_format,
                  )}
                />
                <Metric label="Successful runs" value={String(report.successful_runs)} />
                <Metric label="Failed runs" value={String(report.failed_runs)} />
                <Metric label="Config hash" value={report.config_sha256.slice(0, 12)} />
                <Metric
                  label="Output JSON"
                  value={
                    detail?.output_path || report ? (
                      <Link
                        href={backtestReportUrl(metadata.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        sx={{ wordBreak: 'break-all' }}
                      >
                        {metadata.id.slice(0, 8)}.json
                      </Link>
                    ) : (
                      'Pending write…'
                    )
                  }
                />
              </Stack>
              {sidecarArtifacts(detail?.artifacts ?? []).length > 0 && (
                <Stack spacing={1}>
                  <Typography variant="subtitle2">Sidecar data on disk</Typography>
                  <BacktestArtifactChips artifacts={sidecarArtifacts(detail?.artifacts ?? [])} />
                </Stack>
              )}
              <BacktestCliCommandsSection outputPath={detail?.output_path ?? null} artifacts={detail?.artifacts ?? []} />
              {candidateSummary && (
                <Stack spacing={1}>
                  <Typography variant="subtitle2">Candidate logging</Typography>
                  {candidateSummary.enabledRuns > 0 ? (
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                      <Metric
                        label="Runs with logging"
                        value={`${candidateSummary.enabledRuns}/${report.results.length}`}
                      />
                      <Metric label="Total candidates" value={String(candidateSummary.totalCandidates)} />
                      <Metric label="Traded" value={String(candidateSummary.tradedCandidates)} />
                      <Metric label="Rejected" value={String(candidateSummary.rejectedCandidates)} />
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Not enabled for this backtest. Enable <strong>Include candidate log</strong> in Settings
                      or the wizard to record entry candidates. Select a run below and open the Candidates tab
                      for per-run details.
                    </Typography>
                  )}
                </Stack>
              )}
            </Stack>
          </Paper>

          <BacktestConfigInspector
            backtestId={metadata.id}
            inputConfigPath={report.input_config_path}
            configSha256={report.config_sha256}
            downloadable={metadata.status === 'completed'}
          />

          {resolvedAggregates?.isDerived && (
            <Alert severity="info">
              Batch aggregates were computed in the browser from run results. Re-run this backtest to persist
              strategy-level merged metrics in the report JSON.
            </Alert>
          )}

          {resolvedAggregates?.aggregates.portfolio && (
            <BacktestSummaryDashboard
              portfolio={resolvedAggregates.aggregates.portfolio}
              results={report.results}
              bestRunId={resolvedAggregates.aggregates.portfolio.best_run_id}
              worstRunId={resolvedAggregates.aggregates.portfolio.worst_run_id}
            />
          )}

          <BacktestRunsComparisonTable
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            results={report.results}
            aggregates={resolvedAggregates?.aggregates ?? { portfolio: null, by_strategy: [] }}
            selectedRowId={selectedRowId}
            onSelectRow={setSelectedRowId}
          />

          {selectedRun && (
            <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
              <BacktestRunDetailPanel
                backtestId={metadata?.id ?? backtestId}
                result={selectedRun}
                selection={resolvedSelection}
              />
            </Paper>
          )}

          {selectedStrategyAggregate && resolvedAggregates && (
            <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
              <BacktestStrategyAggregatePanel
                aggregate={selectedStrategyAggregate}
                results={report.results}
                missingMergedRiskMetrics={resolvedAggregates.missingMergedRiskMetrics}
              />
            </Paper>
          )}
        </>
      ) : (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={1} sx={{ alignItems: 'center' }}>
            <Typography>No report payload available yet.</Typography>
          </Stack>
        </Paper>
      )}

      <ConfirmDialog
        open={retryDialogOpen}
        title={isActive ? 'Run again?' : 'Retry backtest?'}
        intent="info"
        icon={<ReplayIcon sx={{ fontSize: 24 }} />}
        description={
          <Typography color="text.secondary">
            This will start a new backtest using the same configuration. The existing run (if any)
            will not be stopped.
          </Typography>
        }
        confirmLabel={isActive ? 'Run again' : 'Retry backtest'}
        cancelLabel="Cancel"
        loading={retrying}
        onCancel={() => {
          if (!retrying) {
            setRetryDialogOpen(false)
          }
        }}
        onConfirm={() => {
          void handleRetry()
        }}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        title="Delete backtest?"
        description={
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
                {resolvedSelection
                  ? `${resolvedSelection.start_date} → ${resolvedSelection.end_date}`
                  : 'Selection summary unavailable'}
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {resolvedSelection
                  ? `${resolvedSelection.symbols?.length ?? 0} symbols · ${resolvedSelection.triggers?.length ?? 0} triggers`
                  : '—'}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                {metadata.id}
              </Typography>
            </Box>
          </Stack>
        }
        confirmLabel="Delete backtest"
        cancelLabel="Keep backtest"
        loading={deleting}
        onCancel={() => {
          if (!deleting) {
            setDeleteDialogOpen(false)
          }
        }}
        onConfirm={() => {
          void confirmDelete()
        }}
      />

      <WorkflowStepsDialog
        open={workflowStepsOpen}
        onClose={() => setWorkflowStepsOpen(false)}
        entityKind="Backtest"
        entityLabel={`Backtest ${metadata.name ?? metadata.id}`}
        workflowName={metadata.workflow_name ?? ''}
        namespace={metadata.workflow_namespace ?? null}
        workflowTitle={metadata.name ?? null}
      />
    </Stack>
  )
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {label}
      </Typography>
      {typeof value === 'string' ? <Typography>{value}</Typography> : value}
    </Box>
  )
}
