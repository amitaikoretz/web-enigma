import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { fetchRiskModelDetail, fetchRiskModelStatus } from '../api/riskModels'
import { BacktestAnalysisSection } from '../components/BacktestAnalysisSection'
import { MetricGrid, type MetricItem, formatMetricNumber } from '../components/BacktestMetricGrid'
import { RiskModelWorkflowErrorDialog } from '../components/RiskModelWorkflowErrorDialog'
import { useSettings } from '../settings/useSettings'
import type {
  RiskModelDetail,
  RiskModelStatusResponse,
  RiskModelStatus,
  RiskModelTargetRow,
} from '../types/riskModels'
import { formatInTimezone } from '../utils/datetime'
import { isRiskModelActive, statusChipColor } from '../utils/riskModels'

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'number') {
    return formatMetricNumber(value, 4)
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  if (typeof value === 'string') {
    return value
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.map((item) => formatMetricValue(item)).join(', ') : '[]'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function flattenMetrics(value: unknown, prefix = ''): MetricItem[] {
  if (!isPlainObject(value)) {
    return prefix ? [{ label: prefix, value: formatMetricValue(value) }] : []
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return prefix ? [{ label: prefix, value: '—' }] : []
  }

  const items: MetricItem[] = []
  for (const [key, nextValue] of entries) {
    const nextPrefix = prefix ? `${prefix}.${key}` : key
    if (isPlainObject(nextValue)) {
      items.push(...flattenMetrics(nextValue, nextPrefix))
      continue
    }
    if (Array.isArray(nextValue)) {
      items.push({ label: nextPrefix, value: formatMetricValue(nextValue) })
      continue
    }
    items.push({ label: nextPrefix, value: formatMetricValue(nextValue) })
  }

  return items
}

function renderMetricGrid(value: unknown): MetricItem[] {
  if (isPlainObject(value)) {
    return flattenMetrics(value)
  }
  return []
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return JSON.stringify(value ?? {}, null, 2)
}

function JsonAccordion({
  title,
  value,
  subtitle,
}: {
  title: string
  value: unknown
  subtitle?: string
}) {
  const content = formatJson(value)

  return (
    <Accordion disableGutters elevation={0} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack spacing={0.25} sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {subtitle}
            </Typography>
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Box
          component="pre"
          sx={{
            m: 0,
            p: 1.5,
            borderRadius: 1,
            bgcolor: 'background.default',
            border: '1px solid',
            borderColor: 'divider',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            lineHeight: 1.55,
            maxHeight: 420,
            overflow: 'auto',
          }}
        >
          {content}
        </Box>
      </AccordionDetails>
    </Accordion>
  )
}

function MetricSection({
  value,
  emptyLabel = 'No metrics available yet.',
}: {
  value: unknown
  emptyLabel?: string
}) {
  const items = renderMetricGrid(value)
  if (items.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        {emptyLabel}
      </Typography>
    )
  }

  return <MetricGrid items={items} minColumnWidth={150} />
}

function TargetCard({
  target,
  timezone,
  timeDisplayFormat,
}: {
  target: RiskModelTargetRow
  timezone: string
  timeDisplayFormat: '12h' | '24h'
}) {
  const metrics = renderMetricGrid(target.metrics)
  const featureColumns = target.feature_columns ?? []

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, bgcolor: 'background.default' }}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}
        >
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
              <Typography variant="h6" component="h3">
                {target.target_key}
              </Typography>
              <Chip size="small" label={target.task_type} variant="outlined" />
              <Chip size="small" label={target.status} color={statusChipColor(target.status as RiskModelStatus)} />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Target row #{target.id} updated {formatTimestamp(target.updated_at, timezone, timeDisplayFormat)}
            </Typography>
          </Stack>
        </Stack>

        <MetricGrid
          items={[
            { label: 'Status', value: target.status },
            { label: 'Task type', value: target.task_type },
            { label: 'Model artifact', value: target.model_artifact_path ?? '—' },
            { label: 'Manifest path', value: target.dataset_manifest_path ?? '—' },
            { label: 'Feature count', value: String(featureColumns.length) },
          ]}
          minColumnWidth={150}
        />

        {featureColumns.length > 0 && (
          <Stack spacing={1}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Feature columns
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
              {featureColumns.slice(0, 16).map((column) => (
                <Chip key={column} size="small" variant="outlined" label={column} sx={{ fontFamily: 'monospace' }} />
              ))}
              {featureColumns.length > 16 && (
                <Chip size="small" label={`+${featureColumns.length - 16} more`} />
              )}
            </Box>
          </Stack>
        )}

        {metrics.length > 0 ? (
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
              Target metrics
            </Typography>
            <MetricGrid items={metrics} minColumnWidth={145} />
          </Box>
        ) : (
          <Typography color="text.secondary" variant="body2">
            Metrics have not been recorded yet for this target.
          </Typography>
        )}

        <Divider />

        <Stack spacing={1}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Artifact details
          </Typography>
          <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
              Model artifact
            </Typography>
            <Box sx={{ fontFamily: 'monospace', p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', wordBreak: 'break-word' }}>
              {target.model_artifact_path ?? '—'}
            </Box>
          </Stack>
          <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
              Dataset manifest
            </Typography>
            <Box sx={{ fontFamily: 'monospace', p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', wordBreak: 'break-word' }}>
              {target.dataset_manifest_path ?? '—'}
            </Box>
          </Stack>
        </Stack>
      </Stack>
    </Paper>
  )
}

export function RiskModelDetailPage() {
  const { platformSettings, appearance } = useSettings()
  const { groupId = '' } = useParams()
  const [detail, setDetail] = useState<RiskModelDetail | null>(null)
  const [status, setStatus] = useState<RiskModelStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorsOpen, setWorkflowErrorsOpen] = useState(false)

  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const timezone = platformSettings.platform_behavior.timezone
  const timeDisplayFormat = appearance.time_display_format

  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchRiskModelDetail(groupId)
        if (cancelled) {
          return
        }
        setDetail(response)
        setStatus({
          group_id: response.group_id,
          status: response.status,
          argo_namespace: response.argo_namespace,
          argo_workflow_name: response.argo_workflow_name,
          argo_phase: null,
        })

        try {
          const nextStatus = await fetchRiskModelStatus(groupId)
          if (!cancelled) {
            setStatus(nextStatus)
          }
        } catch {
          // Status polling is best-effort; the detail page can still render from the main payload.
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load risk model detail')
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
  }, [groupId])

  const activeStatus = status?.status ?? detail?.status ?? null
  const isActive = activeStatus ? isRiskModelActive(activeStatus) : false

  useEffect(() => {
    if (!groupId || !isActive) {
      return undefined
    }

    let cancelled = false

    const poll = async () => {
      try {
        const nextStatus = await fetchRiskModelStatus(groupId)
        if (cancelled) {
          return true
        }

        setStatus(nextStatus)

        if (!isRiskModelActive(nextStatus.status)) {
          const nextDetail = await fetchRiskModelDetail(groupId)
          if (!cancelled) {
            setDetail(nextDetail)
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh risk model status')
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
  }, [groupId, isActive, refreshIntervalMs])

  const manifest = detail?.dataset_manifest ?? null
  const summaryMetrics = detail?.summary_metrics ?? null
  const sourceCount = detail?.sources.length ?? 0
  const targetCount = detail?.targets.length ?? 0
  const hasFailedWorkflow = (detail?.status ?? status?.status) === 'failed'

  const manifestMetrics = useMemo(
    () =>
      manifest
        ? [
            { label: 'Total candidates', value: String(manifest.total_candidates) },
            { label: 'Joined rows', value: String(manifest.joined_rows) },
            { label: 'Labeled rows', value: String(manifest.labeled_rows) },
            { label: 'Feature rows', value: String(manifest.feature_rows) },
            { label: 'Dropped label rows', value: String(manifest.dropped_label_rows) },
            { label: 'Dropped feature rows', value: String(manifest.dropped_feature_rows) },
            { label: 'Duplicate candidate ids', value: String(manifest.duplicate_candidate_ids) },
            { label: 'Config hash', value: manifest.config_hash.slice(0, 12) },
          ]
        : [],
    [manifest],
  )

  if (loading && !detail) {
    return (
      <Stack sx={{ py: 10, alignItems: 'center' }} spacing={1}>
        <CircularProgress />
        <Typography color="text.secondary">Loading risk model detail…</Typography>
      </Stack>
    )
  }

  if (error && !detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="error">{error}</Alert>
        <Button component={RouterLink} to="/risk-models" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to risk models
        </Button>
      </Stack>
    )
  }

  if (!detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="warning">Risk model detail is unavailable.</Alert>
        <Button component={RouterLink} to="/risk-models" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to risk models
        </Button>
      </Stack>
    )
  }

  const statusLabel = status?.argo_phase ?? detail.status

  return (
    <Stack spacing={3}>
      <Paper
        variant="outlined"
        sx={(theme) => ({
          overflow: 'hidden',
          position: 'relative',
          p: { xs: 2.5, md: 3 },
          borderRadius: 3,
          borderColor: theme.palette.divider,
          background: `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.action.hover} 100%)`,
        })}
      >
        <Stack spacing={2}>
          <Button component={RouterLink} to="/risk-models" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
            Back to risk models
          </Button>

          <Stack
            direction={{ xs: 'column', lg: 'row' }}
            spacing={2}
            sx={{ justifyContent: 'space-between', alignItems: { lg: 'flex-start' } }}
          >
            <Stack spacing={1.25} sx={{ maxWidth: 940 }}>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                <Typography variant="h4" component="h1">
                  Risk model {detail.group_id}
                </Typography>
                <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
                {hasFailedWorkflow && <Chip size="small" color="error" variant="outlined" label="workflow failed" />}
              </Stack>
              <Typography color="text.secondary" sx={{ maxWidth: 760 }}>
                Trained from {sourceCount} backtest{sourceCount === 1 ? '' : 's'} with {targetCount}{' '}
                target{targetCount === 1 ? '' : 's'}. This page gathers the training set, labels, metrics,
                and operational metadata for the entire model group.
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} sx={{ flexWrap: 'wrap' }}>
                <Chip label={`Created ${formatTimestamp(detail.created_at, timezone, timeDisplayFormat)}`} variant="outlined" />
                <Chip label={`Updated ${formatTimestamp(detail.updated_at, timezone, timeDisplayFormat)}`} variant="outlined" />
                <Chip label={`Artifact dir ${detail.artifact_dir}`} variant="outlined" sx={{ maxWidth: '100%' }} />
                {detail.argo_namespace && <Chip label={`Namespace ${detail.argo_namespace}`} variant="outlined" />}
                {detail.argo_workflow_name && <Chip label={`Workflow ${detail.argo_workflow_name}`} variant="outlined" />}
              </Stack>
            </Stack>

            <Stack spacing={1} sx={{ minWidth: { xs: '100%', lg: 280 } }}>
              {hasFailedWorkflow && (
                <Button
                  variant="contained"
                  color="error"
                  startIcon={<BugReportOutlinedIcon />}
                  onClick={() => setWorkflowErrorsOpen(true)}
                >
                  View workflow errors
                </Button>
              )}
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                <Stack spacing={0.5}>
                  <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                    Status
                  </Typography>
                  <Typography variant="body1" sx={{ fontWeight: 700 }}>
                    {statusLabel}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {isActive ? 'This model is still updating. The page will refresh until it reaches a terminal state.' : 'This model has reached a terminal state.'}
                  </Typography>
                </Stack>
              </Paper>
            </Stack>
          </Stack>
        </Stack>
      </Paper>

      {error && <Alert severity="error">{error}</Alert>}

      <BacktestAnalysisSection
        title="Training set"
        description="Where the model data came from, how the pooled dataset was built, and what configuration was used to generate it."
      >
        <Stack spacing={2.5}>
          <Stack spacing={1}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Source backtests
            </Typography>
            <Stack spacing={1}>
              {detail.sources.length > 0 ? (
                detail.sources.map((source, index) => (
                  <Paper key={`${source.backtest_id}-${index}`} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                    <Stack spacing={0.75}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                        <Chip
                          size="small"
                          label={`Backtest ${source.backtest_id}`}
                          component={RouterLink}
                          to={`/backtests/${source.backtest_id}`}
                          clickable
                        />
                        <Typography variant="caption" color="text.secondary">
                          Source report: {source.source_report_path ?? '—'}
                        </Typography>
                      </Stack>
                      {source.created_at && (
                        <Typography variant="caption" color="text.secondary">
                          Added {formatTimestamp(source.created_at, timezone, timeDisplayFormat)}
                        </Typography>
                      )}
                    </Stack>
                  </Paper>
                ))
              ) : (
                <Typography color="text.secondary" variant="body2">
                  No source backtests were recorded for this model group.
                </Typography>
              )}
            </Stack>
          </Stack>

          <Stack spacing={1.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Dataset manifest summary
            </Typography>
            {manifest ? (
              <MetricGrid items={manifestMetrics} minColumnWidth={150} />
            ) : (
              <Alert severity="info">No dataset manifest summary is available yet.</Alert>
            )}
          </Stack>

          <JsonAccordion title="Dataset manifest" subtitle={manifest?.output_path} value={manifest} />
          <JsonAccordion title="Training / dataset params" value={detail.params} />
        </Stack>
      </BacktestAnalysisSection>

      <BacktestAnalysisSection
        title="Targets / labels"
        description="A target-by-target view of the trained outputs, label provenance, and feature columns used for each model."
      >
        <Stack spacing={2}>
          {detail.targets.length > 0 ? (
            detail.targets.map((target) => (
              <TargetCard
                key={target.id}
                target={target}
                timezone={timezone}
                timeDisplayFormat={timeDisplayFormat}
              />
            ))
          ) : (
            <Alert severity="info">Targets have not been registered for this model group yet.</Alert>
          )}
        </Stack>
      </BacktestAnalysisSection>

      <BacktestAnalysisSection
        title="Performance metrics"
        description="Headline metrics for the model group, plus the per-target validation metrics recorded during training."
      >
        <Stack spacing={3}>
          <Stack spacing={1.25}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Group-level summary
            </Typography>
            {summaryMetrics ? (
              <MetricSection value={summaryMetrics} />
            ) : (
              <Alert severity="info">No summary metrics are available for this model group yet.</Alert>
            )}
          </Stack>

          <Divider />

          <Stack spacing={1.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Per-target metrics
            </Typography>
            {detail.targets.length > 0 ? (
              <Stack spacing={2}>
                {detail.targets.map((target) => (
                  <Paper key={`metrics-${target.id}`} variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                    <Stack spacing={1.25}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                          {target.target_key}
                        </Typography>
                        <Chip size="small" label={target.task_type} variant="outlined" />
                        <Chip size="small" label={target.status} color={statusChipColor(target.status as RiskModelStatus)} />
                      </Stack>
                      {target.metrics ? (
                        <MetricSection value={target.metrics} emptyLabel="No target metrics available." />
                      ) : (
                        <Typography color="text.secondary" variant="body2">
                          No target metrics available.
                        </Typography>
                      )}
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            ) : (
              <Typography color="text.secondary" variant="body2">
                No per-target metrics are available yet.
              </Typography>
            )}
          </Stack>
        </Stack>
      </BacktestAnalysisSection>

      <BacktestAnalysisSection
        title="Relevant info"
        description="Operational context, raw configuration, and the model registry metadata needed to troubleshoot or inspect this training run."
      >
        <Stack spacing={2}>
          <MetricGrid
            items={[
              { label: 'Artifact directory', value: detail.artifact_dir },
              { label: 'Namespace', value: detail.argo_namespace ?? '—' },
              { label: 'Workflow', value: detail.argo_workflow_name ?? '—' },
              { label: 'Status', value: statusLabel },
              { label: 'Backtests', value: String(sourceCount) },
              { label: 'Targets', value: String(targetCount) },
            ]}
            minColumnWidth={150}
          />

          <Stack spacing={1.5}>
            <JsonAccordion title="Raw params" value={detail.params} />
            <JsonAccordion title="Raw summary metrics" value={summaryMetrics} />
          </Stack>

          {hasFailedWorkflow ? (
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" startIcon={<BugReportOutlinedIcon />} onClick={() => setWorkflowErrorsOpen(true)}>
                  View errors
                </Button>
              }
            >
              The workflow failed. Open the workflow errors dialog to inspect the captured Argo outputs.
            </Alert>
          ) : (
            <Alert severity="info">
              Workflow errors remain available separately if this model later enters a failed state.
            </Alert>
          )}
        </Stack>
      </BacktestAnalysisSection>

      <RiskModelWorkflowErrorDialog
        groupId={workflowErrorsOpen ? detail.group_id : null}
        open={workflowErrorsOpen}
        onClose={() => setWorkflowErrorsOpen(false)}
      />
    </Stack>
  )
}
