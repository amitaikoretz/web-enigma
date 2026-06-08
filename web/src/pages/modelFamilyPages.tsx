import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import LaunchIcon from '@mui/icons-material/Launch'
import ReplayIcon from '@mui/icons-material/Replay'
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
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
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { ConfirmDialog } from '../components/ConfirmDialog'
import { ModelWorkflowErrorDialog } from '../components/ModelWorkflowErrorDialog'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import { FeatureImportanceTab } from '../components/FeatureImportanceTab'
import { useSettings } from '../settings/useSettings'
import type {
  ModelCreateResponse,
  ModelDetail,
  ModelListItem,
  ModelStatus,
  ModelStatusResponse,
  ModelTargetRow,
  ModelWorkflowErrorResponse,
} from '../types/modelFamilies'
import { formatInTimezone } from '../utils/datetime'
import { isModelActive, resolveModelStatus, statusChipColor } from '../utils/modelStatus'
import { formatMetricNumber } from '../components/BacktestMetricGrid'

export interface ModelFamilyConfig {
  singularLabel: string
  pluralLabel: string
  listPath: string
  fetchModels?: () => Promise<ModelListItem[]>
  fetchModelStatus: (groupId: string) => Promise<ModelStatusResponse>
  fetchModelDetail?: (groupId: string) => Promise<ModelDetail>
  fetchModelWorkflowErrors: (groupId: string) => Promise<ModelWorkflowErrorResponse>
  retryModel?: (groupId: string) => Promise<ModelCreateResponse>
  deleteModel?: (groupId: string) => Promise<void>
  updateModelName?: (groupId: string, name: string | null) => Promise<ModelDetail>
}

type MainTab = 'overview' | 'training' | 'targets' | 'performance' | 'feature-importance' | 'debug'
type FeatureBrowserTab = 'summary' | 'groups' | 'all'
type DetailMetricsTab = 'summary' | 'folds'

interface MetricRow {
  path: string
  label: string
  value: string
  description: string
}

interface MetricSection {
  title: string
  description: string
  rows: MetricRow[]
}

const MAIN_TABS: Array<{ id: MainTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'training', label: 'Training' },
  { id: 'targets', label: 'Targets' },
  { id: 'performance', label: 'Performance' },
  { id: 'feature-importance', label: 'Feature Importance' },
  { id: 'debug', label: 'Debug' },
]

function lowerLabel(value: string): string {
  return value.trim().toLowerCase()
}

function normalizedName(value?: string | null): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function entityLabelForModel(singularLabel: string, groupId: string, name?: string | null): string {
  const displayName = normalizedName(name)
  return displayName ? `${singularLabel} ${displayName}` : `${singularLabel} ${groupId}`
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
    if (value.length === 0) {
      return '[]'
    }
    if (value.every((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item))) {
      return value.map((item) => formatMetricValue(item)).join(', ')
    }
    return JSON.stringify(value)
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function flattenMetrics(value: unknown, prefix = ''): Array<{ label: string; value: string }> {
  if (!isPlainObject(value)) {
    return prefix ? [{ label: prefix, value: formatMetricValue(value) }] : []
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return prefix ? [{ label: prefix, value: '—' }] : []
  }

  const items: Array<{ label: string; value: string }> = []
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

function renderMetricGrid(value: unknown): Array<{ label: string; value: string }> {
  const flattened = stripFoldMetrics(value)
  if (!flattened) {
    return []
  }
  return flattenMetrics(flattened)
}

function collectMetricEntries(value: unknown, prefix = ''): Array<{ path: string; value: unknown }> {
  if (!isPlainObject(value)) {
    return prefix ? [{ path: prefix, value }] : []
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return prefix ? [{ path: prefix, value: null }] : []
  }

  const items: Array<{ path: string; value: unknown }> = []
  for (const [key, nextValue] of entries) {
    const nextPath = prefix ? `${prefix}.${key}` : key
    if (isPlainObject(nextValue)) {
      items.push(...collectMetricEntries(nextValue, nextPath))
      continue
    }
    if (Array.isArray(nextValue)) {
      items.push({ path: nextPath, value: nextValue })
      continue
    }
    items.push({ path: nextPath, value: nextValue })
  }

  return items
}

function metricSectionTitle(path: string): string {
  if (path === 'generated_at' || path === 'group_id' || path === 'n_rows' || path === 'positive_rate') {
    return 'Run metadata'
  }
  if (path.startsWith('walk_forward.')) {
    return 'Walk-forward setup'
  }
  if (path.startsWith('aggregate.validation.')) {
    return 'Validation aggregate'
  }
  if (path.startsWith('aggregate.test.')) {
    return 'Test aggregate'
  }
  if (path.startsWith('validation.')) {
    return 'Validation metrics'
  }
  if (path.startsWith('test.')) {
    return 'Test metrics'
  }

  const leaf = path.split('.').at(-1) ?? path
  if (['mae', 'rmse', 'mse', 'mae_abs', 'mae_pct', 'mae_atr'].includes(leaf)) {
    return 'Error metrics'
  }
  if (
    leaf.includes('auc') ||
    leaf.includes('brier') ||
    leaf.includes('logloss') ||
    leaf.includes('calibrat') ||
    leaf.includes('reliability')
  ) {
    return 'Calibration metrics'
  }
  if (leaf.startsWith('underpred_rate') || leaf.includes('coverage') || leaf.includes('quantile')) {
    return 'Tail behavior'
  }
  return 'Other metrics'
}

function metricSectionDescription(title: string): string {
  switch (title) {
    case 'Run metadata':
      return 'Basic context about the training run and the data bundle that produced the metrics.'
    case 'Walk-forward setup':
      return 'How the training windows were sliced for walk-forward validation.'
    case 'Validation aggregate':
      return 'Metrics averaged across validation folds.'
    case 'Test aggregate':
      return 'Metrics averaged across test folds.'
    case 'Validation metrics':
      return 'Per-fold validation metrics for the selected target.'
    case 'Test metrics':
      return 'Per-fold test metrics for the selected target.'
    case 'Calibration metrics':
      return 'How well predicted probabilities line up with the observed outcomes.'
    case 'Error metrics':
      return 'How far predictions miss the realized target values on average.'
    case 'Tail behavior':
      return 'How the model behaves on the most extreme or highest-risk cases.'
    default:
      return 'Additional recorded model metrics.'
  }
}

function metricDescription(path: string): string {
  const leaf = path.split('.').at(-1) ?? path
  const scope = path.startsWith('aggregate.validation.')
    ? 'validation folds'
    : path.startsWith('aggregate.test.')
      ? 'test folds'
      : path.startsWith('validation.')
        ? 'validation fold'
        : path.startsWith('test.')
          ? 'test fold'
          : null

  switch (leaf) {
    case 'generated_at':
      return 'Timestamp when this metrics bundle was generated.'
    case 'group_id':
      return 'Model group identifier tied to this metrics bundle.'
    case 'n_rows':
      return 'Number of rows used to train and evaluate the model.'
    case 'positive_rate':
      return 'Fraction of rows with a positive stop label in the training data.'
    case 'timestamp_column':
      return 'Source timestamp column used to order rows before walk-forward splitting.'
    case 'train_days':
      return 'Length of each training window in days.'
    case 'test_days':
      return 'Length of each validation/test window in days.'
    case 'step_days':
      return 'How far the walk-forward window advances between folds.'
    case 'calibration_fraction':
      return 'Fraction of the training window held back for calibration, when used.'
    case 'embargo_bars':
      return 'Gap inserted to avoid label leakage across adjacent windows.'
    case 'n_folds':
      return 'Total number of walk-forward folds generated for this run.'
    case 'selected_fold_id':
      return 'Fold chosen for the final model artifact.'
    case 'mae_mean':
      return scope ? `Average mean absolute error across ${scope}.` : 'Average mean absolute error.'
    case 'rmse_mean':
      return scope ? `Average root mean squared error across ${scope}.` : 'Average root mean squared error.'
    case 'auc_calibrated_mean':
      return scope
        ? `Average ROC AUC of calibrated stop probabilities across ${scope}.`
        : 'ROC AUC of calibrated stop probabilities.'
    case 'brier_calibrated_mean':
      return scope
        ? `Average Brier score of calibrated stop probabilities across ${scope}.`
        : 'Brier score of calibrated stop probabilities.'
    case 'logloss_calibrated_mean':
      return scope
        ? `Average log loss of calibrated stop probabilities across ${scope}.`
        : 'Log loss of calibrated stop probabilities.'
    case 'underpred_rate_q90_mean':
      return scope
        ? `Average share of q90 tail cases where the model under-predicted MAE across ${scope}.`
        : 'Share of q90 tail cases where the model under-predicted MAE.'
    case 'underpred_rate_q95_mean':
      return scope
        ? `Average share of q95 tail cases where the model under-predicted MAE across ${scope}.`
        : 'Share of q95 tail cases where the model under-predicted MAE.'
    case 'auc_calibrated':
      return 'ROC AUC for the calibrated stop probability; higher is better.'
    case 'brier_calibrated':
      return 'Brier score for the calibrated stop probability; lower is better.'
    case 'brier_raw':
      return 'Brier score before calibration, used to compare raw and calibrated probabilities.'
    case 'logloss_calibrated':
      return 'Log loss for the calibrated stop probability; lower is better.'
    case 'reliability_bins':
      return 'Calibration-curve bins comparing predicted probabilities with observed event rates.'
    case 'mae':
      return 'Mean absolute error of the prediction; lower is better.'
    case 'rmse':
      return 'Root mean squared error of the prediction; lower is better and penalizes large misses more.'
    case 'underpred_rate_q90':
      return 'Share of the top-10% realized MAE cases where the prediction was too low.'
    case 'underpred_rate_q95':
      return 'Share of the top-5% realized MAE cases where the prediction was too low.'
    default:
      break
  }

  if (leaf.startsWith('underpred_rate_')) {
    return 'Share of high-MAE cases where the model under-predicted the realized error.'
  }
  if (leaf === 'mae_mean' || leaf === 'rmse_mean') {
    return `Average ${leaf.replace('_mean', '').toUpperCase()} across ${scope ?? 'the recorded folds'}.`
  }
  if (leaf.includes('auc') || leaf.includes('brier') || leaf.includes('logloss')) {
    return 'Probability-quality metric recorded for the model.'
  }
  if (leaf.includes('mae') || leaf.includes('rmse')) {
    return 'Prediction-error metric recorded for the model.'
  }
  return 'Recorded model metric.'
}

function formatMetricLabel(path: string): string {
  const leaf = path.split('.').at(-1) ?? path
  const tokens = leaf.split('_').filter(Boolean)

  if (tokens.length === 0) {
    return path
  }

  const acronymTokens = new Set(['auc', 'mae', 'mse', 'rmse', 'pnl', 'r2'])
  const titleCaseToken = (token: string, isFirst: boolean) => {
    const lower = token.toLowerCase()
    if (lower === 'logloss') {
      return isFirst ? 'Log loss' : 'loss'
    }
    if (acronymTokens.has(lower) || /^q\d+$/i.test(lower)) {
      return lower.toUpperCase()
    }
    if (lower === 'raw' || lower === 'mean' || lower === 'median' || lower === 'std') {
      return lower
    }
    if (isFirst) {
      return `${lower[0].toUpperCase()}${lower.slice(1)}`
    }
    return lower
  }

  return tokens.map((token, index) => titleCaseToken(token, index === 0)).join(' ')
}

function buildMetricSections(value: unknown): MetricSection[] {
  const entries = collectMetricEntries(value).filter((entry) => !entry.path.endsWith('fold_metrics'))
  if (entries.length === 0) {
    return []
  }

  const sections = new Map<string, MetricSection>()
  for (const entry of entries) {
    const title = metricSectionTitle(entry.path)
    const current = sections.get(title) ?? {
      title,
      description: metricSectionDescription(title),
      rows: [],
    }
    current.rows.push({
      path: entry.path,
      label: formatMetricLabel(entry.path),
      value: formatMetricValue(entry.value),
      description: metricDescription(entry.path),
    })
    sections.set(title, current)
  }

  return [...sections.values()].map((section) => ({
    ...section,
    rows: section.rows.sort((left, right) => left.label.localeCompare(right.label)),
  }))
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
  const maps = folds.map((fold) => buildMetricMap(fold[section])).filter((map) => map.size > 0)
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

function buildFeatureGroups(columns: string[]) {
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
  rows: Array<{ label: string; value: string; mono?: boolean }>
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

function MetricTable({
  rows,
  emptyLabel = '—',
}: {
  rows: MetricRow[]
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
      <Table size="small" aria-label="metric table">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700, width: { xs: '34%', md: '26%' } }}>Metric</TableCell>
            <TableCell sx={{ fontWeight: 700, width: { xs: '18%', md: '16%' } }}>Value</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>What it is</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.path} sx={{ '&:last-child td': { borderBottom: 0 } }}>
              <TableCell
                component="th"
                scope="row"
                sx={{
                  verticalAlign: 'top',
                  minWidth: 0,
                }}
              >
                <Tooltip title={row.path} arrow placement="top-start">
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        lineHeight: 1.35,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {row.label}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        display: 'block',
                        fontFamily: 'monospace',
                        lineHeight: 1.3,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {row.path}
                    </Typography>
                  </Box>
                </Tooltip>
              </TableCell>
              <TableCell sx={{ verticalAlign: 'top' }}>
                <Typography
                  variant="body2"
                  sx={{
                    fontFamily: 'monospace',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {row.value}
                </Typography>
              </TableCell>
              <TableCell sx={{ verticalAlign: 'top', color: 'text.secondary' }}>{row.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

function MetricSectionGroup({ sections }: { sections: MetricSection[] }) {
  if (sections.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        No metrics available yet.
      </Typography>
    )
  }

  return (
    <Stack spacing={1.5}>
      {sections.map((section) => (
        <Paper key={section.title} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
          <Stack spacing={1.25}>
            <Stack spacing={0.25}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {section.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {section.description}
              </Typography>
            </Stack>
            <MetricTable rows={section.rows} />
          </Stack>
        </Paper>
      ))}
    </Stack>
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
                <Box sx={{ display: 'grid', gap: 1.5 }}>
                  <Paper variant="outlined" sx={{ p: 1.25, bgcolor: 'background.paper' }}>
                    <Stack spacing={0.75}>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                        Validation
                      </Typography>
                      <MetricSectionGroup sections={buildMetricSections(fold.validation)} />
                    </Stack>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.25, bgcolor: 'background.paper' }}>
                    <Stack spacing={0.75}>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                        Test
                      </Typography>
                      <MetricSectionGroup sections={buildMetricSections(fold.test)} />
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
  const sections = buildMetricSections(value)
  if (sections.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        {emptyLabel}
      </Typography>
    )
  }

  return <MetricSectionGroup sections={sections} />
}

function TargetCard({
  target,
  timezone,
  timeDisplayFormat,
}: {
  target: ModelTargetRow
  timezone: string
  timeDisplayFormat: '12h' | '24h'
}) {
  const metricSections = buildMetricSections(target.metrics)
  const foldMetrics = getFoldMetrics(target.metrics)
  const featureColumns = target.feature_columns ?? []
  const [metricsTab, setMetricsTab] = useState<DetailMetricsTab>('summary')

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, bgcolor: 'background.default' }}>
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
            <Typography variant="h6" component="h3">
              {target.target_key}
            </Typography>
            <Chip size="small" label={target.task_type} variant="outlined" />
            <Chip size="small" label={target.status} color={statusChipColor(target.status as ModelStatus)} />
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
          {metricSections.length === 0 && foldMetrics.length === 0 ? (
            <Typography color="text.secondary" variant="body2">
              Metrics have not been recorded yet for this target.
            </Typography>
          ) : (
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
              <Stack spacing={1.5}>
                <Tabs
                  value={metricsTab}
                  onChange={(_, nextTab: DetailMetricsTab) => setMetricsTab(nextTab)}
                  variant="scrollable"
                  allowScrollButtonsMobile
                  sx={{ minHeight: 40 }}
                >
                  <Tab value="summary" label="Summary" />
                  <Tab value="folds" label={`Fold metrics (${foldMetrics.length})`} />
                </Tabs>

                {metricsTab === 'summary' ? (
                  metricSections.length > 0 ? (
                    <MetricSectionGroup sections={metricSections} />
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

function ModelListContent({ config }: { config: ModelFamilyConfig }) {
  const navigate = useNavigate()
  const { platformSettings } = useSettings()
  const [items, setItems] = useState<ModelListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorGroupId, setWorkflowErrorGroupId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ModelListItem | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)

  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  async function refreshModels() {
    const fetchModels = config.fetchModels
    if (!fetchModels) {
      throw new Error('Model list fetcher is not configured')
    }

    const result = await fetchModels()
    const activeRows = result.filter((item) => isModelActive(item.status))

    if (activeRows.length === 0) {
      setItems(result)
      return result
    }

    const statusResults = await Promise.allSettled(
      activeRows.map(async (item) => ({
        groupId: item.group_id,
        status: await config.fetchModelStatus(item.group_id),
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
        status: resolveModelStatus(current.status, status.argo_phase),
      })
    }

    const merged = result.map((item) => nextByGroup.get(item.group_id) ?? item)
    setItems(merged)
    return merged
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let cancelled = false
    void refreshModels()
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : `Failed to load ${lowerLabel(config.pluralLabel)}`)
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
  }, [config])

  const hasActive = useMemo(() => items.some((i) => isModelActive(i.status)), [items])

  // eslint-disable-next-line react-hooks/exhaustive-deps
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
          setError(err instanceof Error ? err.message : `Failed to refresh ${lowerLabel(config.pluralLabel)}`)
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
  }, [hasActive, refreshIntervalMs, config])

  function openDetail(groupId: string) {
    setWorkflowErrorGroupId(null)
    navigate(`${config.listPath}/${groupId}`)
  }

  function openWorkflowErrors(groupId: string) {
    setWorkflowErrorGroupId(groupId)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    const groupId = deleteTarget.group_id
    setDeletingId(groupId)
    setError(null)
    try {
      if (!config.deleteModel) {
        throw new Error('Delete action is not configured')
      }
      await config.deleteModel(groupId)
      setDeleteTarget(null)
      await refreshModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to delete ${lowerLabel(config.singularLabel)}`)
    } finally {
      setDeletingId(null)
    }
  }

  async function retryModel(groupId: string) {
    setRetryingId(groupId)
    setError(null)
    try {
      if (!config.retryModel) {
        throw new Error('Retry action is not configured')
      }
      await config.retryModel(groupId)
      await refreshModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to retry ${lowerLabel(config.singularLabel)}`)
    } finally {
      setRetryingId(null)
    }
  }

  const rows = useMemo(() => items, [items])
  const singularLower = lowerLabel(config.singularLabel)
  const pluralLower = lowerLabel(config.pluralLabel)

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography variant="h4">{config.pluralLabel}</Typography>
        <Typography color="text.secondary">
          Trained models from one or more backtests. Click a row for details.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper variant="outlined">
        {loading ? (
          <Stack sx={{ py: 6, alignItems: 'center' }} spacing={1.5}>
            <CircularProgress />
            <Typography color="text.secondary">Loading {pluralLower}…</Typography>
          </Stack>
        ) : rows.length === 0 ? (
          <Box sx={{ p: 3 }}>
            <Typography color="text.secondary">No {pluralLower} yet.</Typography>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Group</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Progress</TableCell>
                <TableCell>Backtests</TableCell>
                <TableCell>Training range</TableCell>
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
                  onClick={() => openDetail(item.group_id)}
                >
                  <TableCell sx={{ fontFamily: 'monospace' }}>{item.group_id}</TableCell>
                  <TableCell>{normalizedName(item.name) ?? '—'}</TableCell>
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
                      ) : isModelActive(item.status) ? (
                        <LinearProgress variant="indeterminate" />
                      ) : (
                        <Typography variant="caption" color="text.secondary">
                          —
                        </Typography>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>{item.backtest_ids.length}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {formatTrainingDateRange(item.training_start_date, item.training_end_date)}
                  </TableCell>
                  <TableCell>{item.targets.join(', ')}</TableCell>
                  <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <Tooltip title="Open details">
                      <IconButton
                        size="small"
                        aria-label="Open details"
                        onClick={() => openDetail(item.group_id)}
                      >
                        <LaunchIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {item.status === 'failed' && (
                      <Tooltip title="Workflow errors">
                        <span>
                          <IconButton
                            size="small"
                            color="error"
                            aria-label="Workflow errors"
                            onClick={() => openWorkflowErrors(item.group_id)}
                          >
                            <BugReportOutlinedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    )}
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
                          aria-label={`Delete ${singularLower}`}
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

      <ModelWorkflowErrorDialog
        groupId={workflowErrorGroupId}
        open={workflowErrorGroupId !== null}
        onClose={() => setWorkflowErrorGroupId(null)}
        entityKind={config.singularLabel}
        entityLabel={workflowErrorGroupId ? `${config.singularLabel} ${workflowErrorGroupId}` : config.singularLabel}
        fetchWorkflowErrors={config.fetchModelWorkflowErrors}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={
          deleteTarget
            ? `Delete ${singularLower} ${normalizedName(deleteTarget.name) ?? deleteTarget.group_id}?`
            : `Delete ${singularLower}`
        }
        intent="error"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
        loading={deleteTarget ? deletingId === deleteTarget.group_id : false}
        description={
          <Typography color="text.secondary">
            This deletes the {singularLower} group, its DB rows, and its artifact directory. If it is running, its
            Argo workflow will be terminated best-effort.
          </Typography>
        }
      />
    </Stack>
  )
}

function ModelDetailContent({ config }: { config: ModelFamilyConfig }) {
  const { platformSettings, appearance } = useSettings()
  const navigate = useNavigate()
  const { groupId = '' } = useParams()
  const [detail, setDetail] = useState<ModelDetail | null>(null)
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflowErrorsOpen, setWorkflowErrorsOpen] = useState(false)
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [mainTab, setMainTab] = useState<MainTab>('overview')
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const timezone = platformSettings.platform_behavior.timezone
  const timeDisplayFormat = appearance.time_display_format
  const singularLower = lowerLabel(config.singularLabel)
  const pluralLower = lowerLabel(config.pluralLabel)

  async function refreshDetail(isCancelled?: () => boolean) {
    const fetchModelDetail = config.fetchModelDetail
    if (!fetchModelDetail) {
      throw new Error('Model detail fetcher is not configured')
    }

    const response = await fetchModelDetail(groupId)
    if (isCancelled?.()) {
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
      const nextStatus = await config.fetchModelStatus(groupId)
      if (!isCancelled?.()) {
        setStatus(nextStatus)
      }
    } catch {
      // Status polling is best-effort; the detail page can still render from the main payload.
    }
  }

  async function confirmRetry() {
    if (!detail || !config.retryModel) {
      return
    }

    setRetrying(true)
    setError(null)
    try {
      await config.retryModel(detail.group_id)
      setRetryDialogOpen(false)
      await refreshDetail()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to retry ${singularLower}`)
    } finally {
      setRetrying(false)
    }
  }

  async function confirmDelete() {
    if (!detail || !config.deleteModel) {
      return
    }

    setDeleting(true)
    setError(null)
    try {
      await config.deleteModel(detail.group_id)
      setDeleteDialogOpen(false)
      navigate(config.listPath)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to delete ${singularLower}`)
    } finally {
      setDeleting(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        await refreshDetail(() => cancelled)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : `Failed to load ${singularLower} detail`)
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
  }, [config, groupId, singularLower])

  useEffect(() => {
    setNameDraft((detail?.name ?? '').toString())
  }, [detail?.name])

  const activeStatus = status?.status ?? detail?.status ?? null
  const isActive = activeStatus ? isModelActive(activeStatus) : false

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!groupId || !isActive) {
      return undefined
    }

    let cancelled = false

    const poll = async () => {
      try {
        const nextStatus = await config.fetchModelStatus(groupId)
        if (cancelled) {
          return true
        }

        setStatus(nextStatus)

        if (!isModelActive(nextStatus.status)) {
          const fetchModelDetail = config.fetchModelDetail
          if (!fetchModelDetail) {
            throw new Error('Model detail fetcher is not configured')
          }
          const nextDetail = await fetchModelDetail(groupId)
          if (!cancelled) {
            setDetail(nextDetail)
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : `Failed to refresh ${singularLower} status`)
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
  }, [config, groupId, isActive, refreshIntervalMs, singularLower])

  const manifest = detail?.dataset_manifest ?? null
  const summaryMetrics = detail?.summary_metrics ?? null
  const sourceCount = detail?.sources.length ?? 0
  const targetCount = detail?.targets.length ?? 0
  const hasFailedWorkflow = (detail?.status ?? status?.status) === 'failed'
  const trainingRange = formatTrainingDateRange(detail?.training_start_date, detail?.training_end_date)
  const detailName = normalizedName(detail?.name)
  const detailDisplayLabel = detail ? entityLabelForModel(config.singularLabel, detail.group_id, detail.name) : ''
  const trimmedNameDraft = nameDraft.trim()
  const normalizedCurrentName = (detail?.name ?? '').toString()
  const normalizedNameDraft = trimmedNameDraft ? trimmedNameDraft : ''
  const nameDirty = Boolean(detail) && normalizedNameDraft !== normalizedCurrentName

  async function saveName() {
    if (!detail || !config.updateModelName || !nameDirty) {
      return
    }

    setSavingName(true)
    setError(null)
    try {
      const updated = await config.updateModelName(detail.group_id, trimmedNameDraft ? trimmedNameDraft : null)
      setDetail(updated)
      setStatus((current) =>
        current
          ? {
              ...current,
              name: updated.name ?? null,
            }
          : current,
      )
      setRenameDialogOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to update ${singularLower} name`)
    } finally {
      setSavingName(false)
    }
  }

  const overviewRows = useMemo(
    () => [
      { label: 'Name', value: detailName ?? '—' },
      { label: 'Status', value: detail?.status ?? '—' },
      { label: 'Argo phase', value: status?.argo_phase ?? '—' },
      { label: 'Created', value: detail ? formatTimestamp(detail.created_at, timezone, timeDisplayFormat) : '—' },
      { label: 'Updated', value: detail ? formatTimestamp(detail.updated_at, timezone, timeDisplayFormat) : '—' },
      { label: 'Training range', value: trainingRange },
      { label: 'Sources', value: String(sourceCount) },
      { label: 'Targets', value: String(targetCount) },
      { label: 'Dataset version', value: manifest?.dataset_version ?? '—' },
    ],
    [
      detail,
      detailName,
      sourceCount,
      status?.argo_phase,
      targetCount,
      timeDisplayFormat,
      timezone,
      trainingRange,
      manifest?.dataset_version,
    ],
  )

  const summaryMetricSections = useMemo(() => buildMetricSections(summaryMetrics), [summaryMetrics])

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
        <Typography color="text.secondary">Loading {singularLower} detail…</Typography>
      </Stack>
    )
  }

  if (error && !detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="error">{error}</Alert>
        <Button component={RouterLink} to={config.listPath} startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to {pluralLower}
        </Button>
      </Stack>
    )
  }

  if (!detail) {
    return (
      <Stack spacing={2}>
        <Alert severity="warning">{config.singularLabel} detail is unavailable.</Alert>
        <Button component={RouterLink} to={config.listPath} startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to {pluralLower}
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
            <Button component={RouterLink} to={config.listPath} startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
              Back to {pluralLower}
            </Button>

            <Stack spacing={1.25}>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                <Stack spacing={0.25}>
                  <Typography variant="h4" component="h1">
                    {detailName ?? `${config.singularLabel} ${detail.group_id}`}
                  </Typography>
                  {detailName && (
                    <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                      {detail.group_id}
                    </Typography>
                  )}
                </Stack>
                <Chip size="small" label={detail.status} color={statusChipColor(detail.status)} />
                {status?.argo_phase && <Chip size="small" label={status.argo_phase} variant="outlined" />}
                {hasFailedWorkflow && <Chip size="small" color="error" variant="outlined" label="workflow failed" />}
                {config.updateModelName && (
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setRenameDialogOpen(true)}
                    sx={{ ml: { xs: 0, sm: 1 } }}
                  >
                    Rename
                  </Button>
                )}
                {config.deleteModel && (
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    onClick={() => setDeleteDialogOpen(true)}
                    sx={{ ml: { xs: 0, sm: 1 } }}
                  >
                    Delete
                  </Button>
                )}
              </Stack>
              <Typography color="text.secondary" sx={{ maxWidth: 760 }}>
                Dashboard view for the training set, targets, metrics, and operational metadata behind this{' '}
                {singularLower} group.
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
                    {config.retryModel && (
                      <Button
                        variant="outlined"
                        color="warning"
                        startIcon={<ReplayIcon />}
                        onClick={() => setRetryDialogOpen(true)}
                      >
                        Retry model
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
                  <InfoTable rows={overviewRows} emptyLabel="No overview details are available yet." />
                </Stack>
              </Paper>
            </Box>

            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Headline metrics
                </Typography>
                {summaryMetricSections.length > 0 ? (
                  <MetricSectionGroup sections={summaryMetricSections} />
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
                {summaryMetricSections.length > 0 ? (
                  <MetricSectionGroup sections={summaryMetricSections} />
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
                        <Chip size="small" label={target.status} color={statusChipColor(target.status as ModelStatus)} />
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

        {mainTab === 'feature-importance' && (
          <Stack spacing={2}>
            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.paper' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Feature importance
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  This view reads the persisted importance artifact written with the trained model.
                </Typography>
                <FeatureImportanceTab
                  target={detail.feature_importance ?? null}
                  targets={detail.targets.map((target) => target.feature_importance).filter(Boolean) as NonNullable<
                    typeof detail.targets[number]['feature_importance']
                  >[]}
                />
              </Stack>
            </Paper>
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

      <Dialog
        open={renameDialogOpen}
        onClose={() => {
          if (!savingName) {
            setRenameDialogOpen(false)
          }
        }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Rename {singularLower}</DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          <Stack spacing={1.5} sx={{ pt: 0.5 }}>
            <TextField
              autoFocus
              fullWidth
              label="Name"
              value={nameDraft}
              onChange={(event) => setNameDraft(event.target.value)}
              helperText="Leave blank to clear the model name."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenameDialogOpen(false)} disabled={savingName}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => void saveName()}
            disabled={!nameDirty || savingName}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteDialogOpen}
        title={`Delete ${singularLower} ${detailName ?? detail.group_id}?`}
        intent="error"
        icon={<DeleteOutlineIcon />}
        confirmLabel={`Delete ${config.singularLabel}`}
        cancelLabel="Cancel"
        onCancel={() => {
          if (!deleting) {
            setDeleteDialogOpen(false)
          }
        }}
        onConfirm={() => void confirmDelete()}
        loading={deleting}
        description={
          <Typography color="text.secondary">
            This permanently deletes the {singularLower} group, its DB rows, and its artifact directory. If it is
            running, its Argo workflow will be terminated best-effort.
          </Typography>
        }
      />

      <ConfirmDialog
        open={retryDialogOpen}
        title={`Retry ${singularLower}?`}
        intent="warning"
        icon={<ReplayIcon />}
        confirmLabel="Retry"
        cancelLabel="Cancel"
        onCancel={() => setRetryDialogOpen(false)}
        onConfirm={() => void confirmRetry()}
        loading={retrying}
        description={
          <Stack spacing={1}>
            <Typography color="text.secondary">
              This will submit a new Argo workflow using the stored launch parameters for this model.
            </Typography>
            <Typography color="text.secondary">
              If the workflow request fails, the error will be shown here instead of silently disappearing.
            </Typography>
          </Stack>
        }
      />

      <ModelWorkflowErrorDialog
        groupId={workflowErrorsOpen ? detail.group_id : null}
        open={workflowErrorsOpen}
        onClose={() => setWorkflowErrorsOpen(false)}
        entityKind={config.singularLabel}
        entityLabel={detailDisplayLabel}
        fetchWorkflowErrors={config.fetchModelWorkflowErrors}
      />

      <WorkflowStepsDialog
        open={workflowStepsOpen}
        onClose={() => setWorkflowStepsOpen(false)}
        entityKind={config.singularLabel}
        entityLabel={detailDisplayLabel}
        workflowName={detail.argo_workflow_name ?? ''}
        namespace={detail.argo_namespace ?? null}
        workflowTitle={detailName ? `${detailName} (${detail.group_id})` : detail.group_id}
      />
    </Box>
  )
}

export function createModelListPage(config: ModelFamilyConfig) {
  return function ModelListPage() {
    return <ModelListContent config={config} />
  }
}

export function createModelDetailPage(config: ModelFamilyConfig) {
  return function ModelDetailPage() {
    return <ModelDetailContent config={config} />
  }
}
