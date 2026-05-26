import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Link,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { backtestReportUrl, fetchBacktestDetail, fetchBacktestStatus } from '../api/backtests'
import { BacktestProgressPanel } from '../components/BacktestProgressPanel'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
import { BacktestConfigInspector } from '../components/BacktestConfigInspector'
import { BacktestRunDetailPanel } from '../components/BacktestRunDetailPanel'
import { BacktestRunsComparisonTable } from '../components/BacktestRunsComparisonTable'
import { BacktestStrategyAggregatePanel } from '../components/BacktestStrategyAggregatePanel'
import { BacktestSummaryDashboard } from '../components/BacktestSummaryDashboard'
import { useSettings } from '../settings/useSettings'
import type { BacktestDetailResponse, BacktestListItem } from '../types/backtests'
import type { ComparisonViewMode } from '../utils/backtestAggregates'
import {
  findRunById,
  findStrategyAggregate,
  resolveReportAggregates,
} from '../utils/backtestAggregates'
import { formatInTimezone } from '../utils/datetime'
import { hasPrefillableInputConfig } from '../utils/backtestConfigPrefill'

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

export function BacktestDetailPage() {
  const { platformSettings, appearance } = useSettings()
  const { backtestId = '' } = useParams()
  const [detail, setDetail] = useState<BacktestDetailResponse | null>(null)
  const [metadata, setMetadata] = useState<BacktestListItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ComparisonViewMode>('symbol')
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null)
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
          setMetadata((current) => current ?? response.metadata)
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

        if (status.status === 'completed' || status.status === 'failed') {
          const nextDetail = await fetchBacktestDetail(backtestId)
          if (!cancelled) {
            setDetail(nextDetail)
            setMetadata(nextDetail.metadata)
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
  const canRerun = hasPrefillableInputConfig(report?.input_config)
  const resolvedAggregates = useMemo(
    () => (report ? resolveReportAggregates(report) : null),
    [report],
  )

  const selectedRun =
    report && selectedRowId && viewMode === 'symbol'
      ? findRunById(report.results, selectedRowId)
      : undefined
  const selectedStrategyAggregate =
    resolvedAggregates && selectedRowId && viewMode === 'strategy'
      ? findStrategyAggregate(resolvedAggregates.aggregates, selectedRowId)
      : undefined

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
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Tooltip
              title={
                canRerun
                  ? 'Open the wizard with this backtest configuration'
                  : 'Available after the backtest completes and its configuration is saved.'
              }
            >
              <span>
                <Button
                  component={RouterLink}
                  to={`/backtests/new?from=${metadata.id}`}
                  variant="outlined"
                  startIcon={<ReplayIcon />}
                  disabled={!canRerun}
                >
                  Re-run backtest
                </Button>
              </span>
            </Tooltip>
            <BacktestStatusChip status={metadata.status} />
            {metadata.report_status && <ReportStatusChip status={metadata.report_status} />}
            {metadata.execution_backend === 'argo' && (
              <Chip size="small" label="Argo" color="info" variant="outlined" />
            )}
          </Stack>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {metadata.workflow_name && (
        <Alert severity="info">
          Argo workflow: {metadata.workflow_name}
          {metadata.workflow_namespace ? ` (${metadata.workflow_namespace})` : ''}
        </Alert>
      )}

      {isActive && (
        <BacktestProgressPanel
          completedRuns={metadata.completed_runs}
          totalRuns={metadata.total_runs}
        />
      )}

      {metadata.error_message && metadata.status === 'failed' && (
        <Alert severity="error">{metadata.error_message}</Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Submission summary</Typography>
          {metadata.selection ? (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Metric label="Date range" value={`${metadata.selection.start_date} → ${metadata.selection.end_date}`} />
              <Metric label="Resolution" value={metadata.selection.resolution} />
              <Metric label="Symbols" value={metadata.selection.symbols.join(', ')} />
              <Metric label="Strategies" value={metadata.selection.strategies.join(', ')} />
            </Stack>
          ) : (
            <Typography color="text.secondary">Selection summary unavailable.</Typography>
          )}
        </Stack>
      </Paper>

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
                    detail?.output_path ? (
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
            </Stack>
          </Paper>

          <BacktestConfigInspector
            backtestId={metadata.id}
            inputConfigPath={report.input_config_path}
            configSha256={report.config_sha256}
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
              <BacktestRunDetailPanel result={selectedRun} selection={metadata.selection} />
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
