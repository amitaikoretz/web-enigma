import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
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
  IconButton,
  Paper,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { fetchRiskModelDetail, fetchRiskModelStatus } from '../api/riskModels'
import { type MetricItem, formatMetricNumber } from '../components/BacktestMetricGrid'
import { RiskModelWorkflowErrorDialog } from '../components/RiskModelWorkflowErrorDialog'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import { useSettings } from '../settings/useSettings'
import type {
  RiskModelDetail,
  RiskModelStatusResponse,
  RiskModelStatus,
  RiskModelTargetRow,
} from '../types/riskModels'
import { formatInTimezone } from '../utils/datetime'
import { isRiskModelActive, statusChipColor } from '../utils/riskModels'

type MainTab = 'overview' | 'training' | 'targets' | 'performance' | 'debug'

const MAIN_TABS: Array<{ id: MainTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'training', label: 'Training' },
  { id: 'targets', label: 'Targets' },
  { id: 'performance', label: 'Performance' },
  { id: 'debug', label: 'Debug' },
]

type FeatureBrowserTab = 'summary' | 'groups' | 'all'

interface InfoRow {
  label: string
  value: string
  mono?: boolean
}

interface FeatureGroupSummary {
  group: string
  count: number
  examples: string[]
}

interface FoldMetricEntry {
  fold_id: number
  train_start: string
  train_end: string
  validation_start: string
  validation_end: string
  test_start: string
  test_end: string
  n_train: number
  n_validation: number
  n_test: number
  validation?: Record<string, unknown> | null
  test?: Record<string, unknown> | null
}

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function formatTrainingDateRange(startDate?: string | null, endDate?: string | null): string {
  if (!startDate && !endDate) {
    return '—'
  }
  if (startDate && endDate && startDate === endDate) {
    return startDate
  }
  if (startDate && endDate) {
    return `${startDate} to ${endDate}`
  }
  return startDate ?? endDate ?? '—'
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

function stripFoldMetrics(value: unknown): Record<string, unknown> | null {
  if (!isPlainObject(value)) {
    return null
  }

  const entries = Object.entries(value).filter(([key]) => key !== 'fold_metrics')
  return Object.fromEntries(entries)
}

function renderMetricGrid(value: unknown): MetricItem[] {
  const flattened = stripFoldMetrics(value)
  if (!flattened) {
    return []
  }
  return flattenMetrics(flattened)
}

function getFoldMetrics(value: unknown): FoldMetricEntry[] {
  if (!isPlainObject(value)) {
    return []
  }

  const foldMetrics = value.fold_metrics
  if (!Array.isArray(foldMetrics)) {
    return []
  }

  return foldMetrics.filter((entry): entry is FoldMetricEntry => isPlainObject(entry) && typeof entry.fold_id === 'number')
}

function buildMetricMap(value: unknown): Map<string, string> {
  const rows = renderMetricGrid(value)
  return new Map(rows.map((item) => [item.label, item.value]))
}

function collectCommonMetricLabels(folds: FoldMetricEntry[], section: 'validation' | 'test'): string[] {
  const maps = folds
    .map((fold) => buildMetricMap(fold[section]))
    .filter((map) => map.size > 0)

  if (maps.length === 0) {
    return []
  }

  const common = [...maps[0].keys()].filter((key) => maps.every((map) => map.has(key)))
  return common.sort((left, right) => left.localeCompare(right))
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return JSON.stringify(value ?? {}, null, 2)
}

function featureGroupName(column: string): string {
  const dotIndex = column.indexOf('.')
  const underscoreIndex = column.indexOf('_')
  const candidateIndexes = [dotIndex, underscoreIndex].filter((index) => index > 0)
  if (candidateIndexes.length === 0) {
    return 'Ungrouped'
  }

  const splitIndex = Math.min(...candidateIndexes)
  return splitIndex > 0 ? column.slice(0, splitIndex) : 'Ungrouped'
}

function buildFeatureGroups(columns: string[]): FeatureGroupSummary[] {
  const groups = new Map<string, string[]>()
  for (const column of columns) {
    const group = featureGroupName(column)
    const current = groups.get(group) ?? []
    current.push(column)
    groups.set(group, current)
  }

  return [...groups.entries()]
    .map(([group, values]) => ({
      group,
      count: values.length,
      examples: values.slice(0, 3),
    }))
    .sort((left, right) => right.count - left.count || left.group.localeCompare(right.group))
}

function InfoTable({
  rows,
  emptyLabel = '—',
}: {
  rows: InfoRow[]
  emptyLabel?: string
}) {
  if (rows.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        {emptyLabel}
      </Typography>
    )
  }

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ overflow: 'hidden' }}>
      <Table size="small" aria-label="information table">
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={`${row.label}-${index}`} sx={{ '&:last-child td': { borderBottom: 0 } }}>
              <TableCell
                component="th"
                scope="row"
                sx={{
                  width: { xs: '40%', md: '28%' },
                  fontWeight: 700,
                  color: 'text.secondary',
                  verticalAlign: 'top',
                }}
              >
                {row.label}
              </TableCell>
              <TableCell
                sx={{
                  fontFamily: row.mono ? 'monospace' : 'inherit',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  verticalAlign: 'top',
                }}
              >
                {row.value}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

function FeatureBrowser({ columns }: { columns: string[] }) {
  const [tab, setTab] = useState<FeatureBrowserTab>('summary')
  const groups = useMemo(() => buildFeatureGroups(columns), [columns])
  const ungroupedCount = groups.find((group) => group.group === 'Ungrouped')?.count ?? 0
  const representativeColumns = columns.slice(0, 8)

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 }, bgcolor: 'background.default' }}>
      <Stack spacing={1.5}>
        <Stack spacing={0.25}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Feature browser
          </Typography>
          <Typography color="text.secondary" variant="body2">
            Grouped by prefix so you can scan related features without reading a wall of chips.
          </Typography>
        </Stack>

        <Tabs
          value={tab}
          onChange={(_, nextTab: FeatureBrowserTab) => setTab(nextTab)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ minHeight: 40 }}
        >
          <Tab value="summary" label="Summary" />
          <Tab value="groups" label="Groups" />
          <Tab value="all" label="All" />
        </Tabs>

        {columns.length === 0 ? (
          <Alert severity="info">No feature columns were recorded for this target.</Alert>
        ) : tab === 'summary' ? (
          <Stack spacing={2}>
            <InfoTable
              rows={[
                { label: 'Total columns', value: String(columns.length) },
                { label: 'Groups', value: String(groups.length) },
                { label: 'Ungrouped', value: String(ungroupedCount) },
              ]}
            />
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                Representative columns
              </Typography>
              <Box
                component="ul"
                sx={{
                  m: 0,
                  p: 0,
                  listStyle: 'none',
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1,
                }}
              >
                {representativeColumns.map((column) => (
                  <Box
                    key={column}
                    component="li"
                    sx={{
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 1,
                      bgcolor: 'background.paper',
                      px: 1.25,
                      py: 1,
                    }}
                  >
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>
                      {column}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {featureGroupName(column)}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          </Stack>
        ) : tab === 'groups' ? (
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360, overflow: 'auto' }}>
            <Table stickyHeader size="small" aria-label="feature groups table">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Group</TableCell>
                  <TableCell sx={{ fontWeight: 700, width: 92 }}>Count</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Examples</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {groups.map((group) => (
                  <TableRow key={group.group}>
                    <TableCell>{group.group}</TableCell>
                    <TableCell>{group.count}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {group.examples.join(', ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 420, overflow: 'auto' }}>
            <Table stickyHeader size="small" aria-label="all feature columns table">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, width: 68 }}>#</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Feature</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Group</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {columns.map((column, index) => (
                  <TableRow key={`${column}-${index}`}>
                    <TableCell>{index + 1}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {column}
                    </TableCell>
                    <TableCell>{featureGroupName(column)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>
    </Paper>
  )
}

function FoldMetricsPanel({ value }: { value: unknown }) {
  const folds = useMemo(() => getFoldMetrics(value), [value])
  const comparisonValidationLabels = useMemo(() => collectCommonMetricLabels(folds, 'validation'), [folds])
  const comparisonTestLabels = useMemo(() => collectCommonMetricLabels(folds, 'test'), [folds])

  if (folds.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        No fold metrics were recorded for this target.
      </Typography>
    )
  }

  return (
    <Stack spacing={1.5}>
      <InfoTable rows={[{ label: 'Folds', value: String(folds.length) }]} />
      <Box sx={{ overflowX: 'auto', pb: 0.5 }}>
        <Stack direction="row" spacing={1} sx={{ minWidth: 'max-content' }}>
          {folds.map((fold) => (
            <Paper
              key={`timeline-${fold.fold_id}`}
              variant="outlined"
              sx={{
                px: 1.5,
                py: 1,
                minWidth: 220,
                bgcolor: 'background.paper',
              }}
            >
              <Stack spacing={0.75}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    Fold {fold.fold_id}
                  </Typography>
                  <Chip size="small" variant="outlined" label={`${fold.n_train}/${fold.n_validation}/${fold.n_test}`} />
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  {fold.train_start} → {fold.test_end}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Train {fold.n_train} | Validation {fold.n_validation} | Test {fold.n_test}
                </Typography>
              </Stack>
            </Paper>
          ))}
        </Stack>
      </Box>

      <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Fold comparison
          </Typography>
          <TableContainer component={Box} sx={{ overflowX: 'auto' }}>
            <Table size="small" aria-label="fold comparison table" sx={{ minWidth: 720 }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Fold</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Train</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Validation</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Test</TableCell>
                  {comparisonValidationLabels.slice(0, 3).map((label) => (
                    <TableCell key={`val-${label}`} sx={{ fontWeight: 700 }}>
                      Val {label}
                    </TableCell>
                  ))}
                  {comparisonTestLabels.slice(0, 3).map((label) => (
                    <TableCell key={`test-${label}`} sx={{ fontWeight: 700 }}>
                      Test {label}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {folds.map((fold) => {
                  const validationMap = buildMetricMap(fold.validation)
                  const testMap = buildMetricMap(fold.test)
                  return (
                    <TableRow key={`comparison-${fold.fold_id}`}>
                      <TableCell>{fold.fold_id}</TableCell>
                      <TableCell>{fold.n_train}</TableCell>
                      <TableCell>{fold.n_validation}</TableCell>
                      <TableCell>{fold.n_test}</TableCell>
                      {comparisonValidationLabels.slice(0, 3).map((label) => (
                        <TableCell key={`comparison-${fold.fold_id}-val-${label}`}>
                          {validationMap.get(label) ?? '—'}
                        </TableCell>
                      ))}
                      {comparisonTestLabels.slice(0, 3).map((label) => (
                        <TableCell key={`comparison-${fold.fold_id}-test-${label}`}>
                          {testMap.get(label) ?? '—'}
                        </TableCell>
                      ))}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
          {(comparisonValidationLabels.length > 3 || comparisonTestLabels.length > 3) && (
            <Typography variant="caption" color="text.secondary">
              Showing the first 3 shared metrics for validation and test sections.
            </Typography>
          )}
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        {folds.map((fold) => (
          <Paper key={fold.fold_id} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
            <Stack spacing={1.25}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                  Fold {fold.fold_id}
                </Typography>
                <Chip size="small" variant="outlined" label={`Train ${fold.n_train}`} />
                <Chip size="small" variant="outlined" label={`Validation ${fold.n_validation}`} />
                <Chip size="small" variant="outlined" label={`Test ${fold.n_test}`} />
              </Stack>

              <Box
                sx={{
                  display: 'grid',
                  gap: 1.5,
                  gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' },
                }}
              >
                <InfoTable
                  rows={[
                    { label: 'Train start', value: fold.train_start, mono: true },
                    { label: 'Train end', value: fold.train_end, mono: true },
                    { label: 'Validation start', value: fold.validation_start, mono: true },
                    { label: 'Validation end', value: fold.validation_end, mono: true },
                    { label: 'Test start', value: fold.test_start, mono: true },
                    { label: 'Test end', value: fold.test_end, mono: true },
                  ]}
                />
                <InfoTable
                  rows={[
                    { label: 'Validation metrics', value: 'See structured metrics below' },
                    { label: 'Test metrics', value: 'See structured metrics below' },
                  ]}
                />
                <Box sx={{ display: 'grid', gap: 1.5 }}>
                  <Paper variant="outlined" sx={{ p: 1.25, bgcolor: 'background.paper' }}>
                    <Stack spacing={0.75}>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                        Validation
                      </Typography>
                      <InfoTable rows={renderMetricGrid(fold.validation)} />
                    </Stack>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.25, bgcolor: 'background.paper' }}>
                    <Stack spacing={0.75}>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                        Test
                      </Typography>
                      <InfoTable rows={renderMetricGrid(fold.test)} />
                    </Stack>
                  </Paper>
                </Box>
              </Box>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Stack>
  )
}

async function copyText(value: string): Promise<boolean> {
  if (!value.trim() || !navigator.clipboard?.writeText) {
    return false
  }

  await navigator.clipboard.writeText(value)
  return true
}

function CopyableField({
  label,
  value,
  copyValue,
  mono = false,
  muted = false,
}: {
  label: string
  value: string
  copyValue?: string
  mono?: boolean
  muted?: boolean
}) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    if (!copyValue || copied) {
      return
    }
    try {
      const wasCopied = await copyText(copyValue)
      if (wasCopied) {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1200)
      }
    } catch {
      // Clipboard copy is best-effort.
    }
  }

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
        {label}
      </Typography>
      <Paper
        variant="outlined"
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 1,
          px: 1.25,
          py: 1,
          bgcolor: 'background.default',
        }}
      >
        <Typography
          variant="body2"
          sx={{
            flex: 1,
            minWidth: 0,
            fontFamily: mono ? 'monospace' : 'inherit',
            color: muted ? 'text.secondary' : 'text.primary',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: 1.5,
          }}
        >
          {value}
        </Typography>
        {copyValue && (
          <Tooltip title={copied ? 'Copied' : 'Copy'}>
            <IconButton
              size="small"
              aria-label={`Copy ${label.toLowerCase()}`}
              onClick={() => void handleCopy()}
              sx={{ mt: -0.25, color: copied ? 'success.main' : 'text.secondary' }}
            >
              <ContentCopyIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Paper>
    </Stack>
  )
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
    <Accordion
      disableGutters
      elevation={0}
      sx={{ border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack spacing={0.25} sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
            >
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

  return (
    <InfoTable
      rows={items.map((item) => ({
        label: item.label,
        value: item.value,
      }))}
    />
  )
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
  const foldMetrics = getFoldMetrics(target.metrics)
  const featureColumns = target.feature_columns ?? []
  const [metricsTab, setMetricsTab] = useState<'summary' | 'folds'>('summary')

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, bgcolor: 'background.default' }}>
      <Stack spacing={2}>
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

        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 320px) minmax(0, 1fr)' },
            alignItems: 'start',
          }}
        >
          <Stack spacing={1.5}>
            <InfoTable
              rows={[
                { label: 'Status', value: target.status },
                { label: 'Task type', value: target.task_type },
                { label: 'Feature count', value: String(featureColumns.length) },
              ]}
            />

            <Stack spacing={1}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Artifact details
              </Typography>
              <Stack spacing={1.25}>
                <CopyableField
                  label="Model artifact"
                  value={target.model_artifact_path ?? '—'}
                  copyValue={target.model_artifact_path ?? undefined}
                  mono
                />
                <CopyableField
                  label="Dataset manifest"
                  value={target.dataset_manifest_path ?? '—'}
                  copyValue={target.dataset_manifest_path ?? undefined}
                  mono
                />
              </Stack>
            </Stack>

            <Stack spacing={1}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Feature preview
              </Typography>
              {featureColumns.length > 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
                  {featureColumns.slice(0, 4).join(', ')}
                  {featureColumns.length > 4 ? `, +${featureColumns.length - 4} more` : ''}
                </Typography>
              ) : (
                <Typography color="text.secondary" variant="body2">
                  No feature columns were recorded for this target.
                </Typography>
              )}
            </Stack>
          </Stack>

          <FeatureBrowser columns={featureColumns} />
        </Box>

        <Stack spacing={1}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Target metrics
          </Typography>
          {metrics.length === 0 && foldMetrics.length === 0 ? (
            <Typography color="text.secondary" variant="body2">
              Metrics have not been recorded yet for this target.
            </Typography>
          ) : (
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
              <Stack spacing={1.5}>
                <Tabs
                  value={metricsTab}
                  onChange={(_, nextTab: 'summary' | 'folds') => setMetricsTab(nextTab)}
                  variant="scrollable"
                  allowScrollButtonsMobile
                  sx={{ minHeight: 40 }}
                >
                  <Tab value="summary" label="Summary" />
                  <Tab value="folds" label={`Fold metrics (${foldMetrics.length})`} />
                </Tabs>

                {metricsTab === 'summary' ? (
                  metrics.length > 0 ? (
                    <InfoTable rows={metrics} />
                  ) : (
                    <Typography color="text.secondary" variant="body2">
                      No summary metrics are available for this target.
                    </Typography>
                  )
                ) : (
                  <FoldMetricsPanel value={target.metrics} />
                )}
              </Stack>
            </Paper>
          )}
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
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)
  const [mainTab, setMainTab] = useState<MainTab>('overview')
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
  const trainingRange = formatTrainingDateRange(detail?.training_start_date, detail?.training_end_date)

  const overviewRows = useMemo(
    () => [
      { label: 'Status', value: detail?.status ?? '—' },
      { label: 'Argo phase', value: status?.argo_phase ?? '—' },
      { label: 'Created', value: detail ? formatTimestamp(detail.created_at, timezone, timeDisplayFormat) : '—' },
      { label: 'Updated', value: detail ? formatTimestamp(detail.updated_at, timezone, timeDisplayFormat) : '—' },
      { label: 'Training range', value: trainingRange },
      { label: 'Sources', value: String(sourceCount) },
      { label: 'Targets', value: String(targetCount) },
      { label: 'Dataset version', value: manifest?.dataset_version ?? '—' },
    ],
    [detail, sourceCount, status?.argo_phase, targetCount, timeDisplayFormat, timezone, trainingRange, manifest?.dataset_version],
  )

  const summaryMetricRows = useMemo(() => {
    return renderMetricGrid(summaryMetrics).map((item) => ({
      label: item.label,
      value: item.value,
    }))
  }, [summaryMetrics])

  const manifestRows = useMemo(
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
    <Box
      sx={{
        display: 'grid',
        gap: 3,
        alignItems: 'start',
        gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1fr) 360px' },
      }}
    >
      <Stack spacing={3} sx={{ minWidth: 0 }}>
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

            <Stack spacing={1.25}>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                <Typography variant="h4" component="h1">
                  Risk model {detail.group_id}
                </Typography>
                <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
                {hasFailedWorkflow && <Chip size="small" color="error" variant="outlined" label="workflow failed" />}
              </Stack>
              <Typography color="text.secondary" sx={{ maxWidth: 760 }}>
                Dashboard view for the training set, targets, metrics, and operational metadata behind this risk model
                group.
              </Typography>
              <Tabs
                value={mainTab}
                onChange={(_, nextTab: MainTab) => setMainTab(nextTab)}
                variant="scrollable"
                allowScrollButtonsMobile
                sx={{ minHeight: 40 }}
              >
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
            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: { xs: '1fr', lg: '1.1fr 0.9fr' },
                alignItems: 'start',
              }}
            >
              <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
                <Stack spacing={1.5}>
                  <Stack spacing={0.5}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                      Status
                    </Typography>
                    <Typography color="text.secondary" variant="body2">
                      {isActive
                        ? 'This model is still updating. The page will refresh until it reaches a terminal state.'
                        : 'This model has reached a terminal state.'}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                    <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                    {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
                    {hasFailedWorkflow && <Chip size="small" color="error" variant="outlined" label="workflow failed" />}
                  </Stack>
                  <Divider />
                  <Stack spacing={1}>
                    {detail.argo_workflow_name && (
                      <Button
                        variant="outlined"
                        startIcon={<BugReportOutlinedIcon />}
                        onClick={() => setWorkflowStepsOpen(true)}
                      >
                        View workflow steps
                      </Button>
                    )}
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
                  </Stack>
                  {hasFailedWorkflow ? (
                    <Alert severity="warning">
                      The workflow failed. Open the workflow error dialog to inspect the captured Argo outputs.
                    </Alert>
                  ) : (
                    <Alert severity="info">Workflow diagnostics remain available if this model later fails.</Alert>
                  )}
                </Stack>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Training snapshot
                  </Typography>
                  <InfoTable
                    rows={overviewRows}
                    emptyLabel="No overview details are available yet."
                  />
                </Stack>
              </Paper>
            </Box>

            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Headline metrics
                </Typography>
                {summaryMetricRows.length > 0 ? (
                  <InfoTable rows={summaryMetricRows} />
                ) : (
                  <Alert severity="info">No summary metrics are available for this model group yet.</Alert>
                )}
              </Stack>
            </Paper>
          </Stack>
        )}

        {mainTab === 'training' && (
          <Stack spacing={2}>
            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Source backtests
                </Typography>
                {detail.sources.length > 0 ? (
                  <TableContainer component={Paper} variant="outlined" sx={{ overflow: 'hidden' }}>
                    <Table size="small" aria-label="source backtests table">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 700 }}>Backtest</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Source report</TableCell>
                          <TableCell sx={{ fontWeight: 700, width: 220 }}>Added</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {detail.sources.map((source) => (
                          <TableRow key={source.backtest_id}>
                            <TableCell>
                              <Button
                                component={RouterLink}
                                to={`/backtests/${source.backtest_id}`}
                                size="small"
                                variant="text"
                                sx={{ px: 0, minWidth: 'auto', fontFamily: 'monospace' }}
                              >
                                {source.backtest_id}
                              </Button>
                            </TableCell>
                            <TableCell sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {source.source_report_path ?? '—'}
                            </TableCell>
                            <TableCell>
                              {source.created_at
                                ? formatTimestamp(source.created_at, timezone, timeDisplayFormat)
                                : '—'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography color="text.secondary" variant="body2">
                    No source backtests were recorded for this model group.
                  </Typography>
                )}
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Dataset manifest summary
                </Typography>
                {manifestRows.length > 0 ? (
                  <InfoTable rows={manifestRows} />
                ) : (
                  <Alert severity="info">No dataset manifest summary is available yet.</Alert>
                )}
              </Stack>
            </Paper>
          </Stack>
        )}

        {mainTab === 'targets' && (
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
        )}

        {mainTab === 'performance' && (
          <Stack spacing={2}>
            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Group-level summary
                </Typography>
                {summaryMetricRows.length > 0 ? (
                  <InfoTable rows={summaryMetricRows} />
                ) : (
                  <Alert severity="info">No summary metrics are available for this model group yet.</Alert>
                )}
              </Stack>
            </Paper>

            <Stack spacing={2}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Per-target metrics
              </Typography>
              {detail.targets.length > 0 ? (
                detail.targets.map((target) => (
                  <Paper key={`metrics-${target.id}`} variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
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
                ))
              ) : (
                <Typography color="text.secondary" variant="body2">
                  No per-target metrics are available yet.
                </Typography>
              )}
            </Stack>
          </Stack>
        )}

        {mainTab === 'debug' && (
          <Stack spacing={2}>
            <Alert
              severity="info"
              action={
                detail.argo_workflow_name ? (
                  <Button size="small" variant="outlined" onClick={() => setWorkflowStepsOpen(true)}>
                    View workflow steps
                  </Button>
                ) : undefined
              }
            >
              Raw payloads are tucked away here so the rest of the page stays readable.
            </Alert>

            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Operational metadata
                </Typography>
                <InfoTable
                  rows={[
                    { label: 'Artifact directory', value: detail.artifact_dir, mono: true },
                    { label: 'Namespace', value: detail.argo_namespace ?? '—' },
                    { label: 'Workflow', value: detail.argo_workflow_name ?? '—' },
                    { label: 'Status', value: statusLabel },
                    { label: 'Backtests', value: String(sourceCount) },
                    { label: 'Targets', value: String(targetCount) },
                  ]}
                />
              </Stack>
            </Paper>

            <JsonAccordion title="Raw params" value={detail.params} />
            <JsonAccordion title="Raw summary metrics" value={summaryMetrics} />
            {manifest ? <JsonAccordion title="Raw dataset manifest" subtitle={manifest.output_path} value={manifest} /> : null}
          </Stack>
        )}
      </Stack>

      <Stack spacing={2} sx={{ minWidth: 0, position: { xl: 'sticky' }, top: { xl: 24 }, alignSelf: 'start' }}>
        <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.paper' }}>
          <Stack spacing={1.5}>
            <Stack spacing={0.5}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Status panel
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Keep the operational state in view while scanning the tabbed content.
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
              {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
              {hasFailedWorkflow && <Chip size="small" color="error" variant="outlined" label="workflow failed" />}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {isActive
                ? 'This model is still updating. The page will refresh until it reaches a terminal state.'
                : 'This model has reached a terminal state.'}
            </Typography>
            <Divider />
            <Stack spacing={1}>
              {detail.argo_workflow_name && (
                <Button
                  variant="outlined"
                  startIcon={<BugReportOutlinedIcon />}
                  onClick={() => setWorkflowStepsOpen(true)}
                >
                  View workflow steps
                </Button>
              )}
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
            </Stack>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.paper' }}>
          <Stack spacing={1.25}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Quick facts
            </Typography>
            <InfoTable
              rows={[
                { label: 'Artifact directory', value: detail.artifact_dir, mono: true },
                { label: 'Workflow', value: detail.argo_workflow_name ?? '—' },
                { label: 'Namespace', value: detail.argo_namespace ?? '—' },
                { label: 'Training range', value: trainingRange },
                { label: 'Sources', value: String(sourceCount) },
                { label: 'Targets', value: String(targetCount) },
              ]}
            />
          </Stack>
        </Paper>

        {hasFailedWorkflow ? (
          <Alert severity="warning">
            The workflow failed. Open the workflow error dialog to inspect the captured Argo outputs.
          </Alert>
        ) : (
          <Alert severity="info">Workflow diagnostics remain available if this model later fails.</Alert>
        )}
      </Stack>

      <RiskModelWorkflowErrorDialog
        groupId={workflowErrorsOpen ? detail.group_id : null}
        open={workflowErrorsOpen}
        onClose={() => setWorkflowErrorsOpen(false)}
      />

      <WorkflowStepsDialog
        open={workflowStepsOpen}
        onClose={() => setWorkflowStepsOpen(false)}
        entityKind="Risk model"
        entityLabel={`Risk model ${detail.group_id}`}
        workflowName={detail.argo_workflow_name ?? ''}
        namespace={detail.argo_namespace ?? null}
        workflowTitle={detail.group_id}
      />
    </Box>
  )
}
