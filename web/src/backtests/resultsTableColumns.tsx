import type { ReactNode } from 'react'
import {
  LinearProgress,
  Link,
  Stack,
  Typography,
} from '@mui/material'

import { backtestConfigUrl, backtestReportUrl } from '../api/backtests'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
import type { BacktestListItem } from '../types/backtests'
import type { TimeDisplayFormat } from '../types/settings'
import { formatInTimezone } from '../utils/datetime'
import { formatBacktestWallRuntime } from '../utils/formatDuration'

export const BACKTEST_RESULTS_COLUMN_IDS = [
  'created',
  'status',
  'report',
  'date_range',
  'universe',
  'runs',
  'runtime',
  'json',
  'yaml',
] as const

export type BacktestResultsColumnId = (typeof BACKTEST_RESULTS_COLUMN_IDS)[number]

export const BACKTEST_RESULTS_COLUMN_LABELS: Record<BacktestResultsColumnId, string> = {
  created: 'Created',
  status: 'Status',
  report: 'Report',
  date_range: 'Date range',
  universe: 'Universe',
  runs: 'Runs',
  runtime: 'Runtime',
  json: 'JSON',
  yaml: 'YAML',
}

export const DEFAULT_BACKTEST_RESULTS_TABLE_COLUMNS: BacktestResultsColumnId[] = [
  ...BACKTEST_RESULTS_COLUMN_IDS,
]

export interface BacktestResultsColumnContext {
  timezone: string
  timeDisplayFormat: TimeDisplayFormat
  nowMs: number
}

function formatSelectionCounts(selection: BacktestListItem['selection']): string {
  if (!selection) {
    return '—'
  }
  const symbolCount = selection.symbols?.length ?? 0
  const strategyCount = selection.strategies?.length ?? 0
  return `${symbolCount} symbols / ${strategyCount} strategies`
}

export interface BacktestResultsColumnDefinition {
  id: BacktestResultsColumnId
  label: string
  align?: 'left' | 'right'
  minWidth?: number
  render: (item: BacktestListItem, ctx: BacktestResultsColumnContext) => ReactNode
}

export const BACKTEST_RESULTS_COLUMNS: BacktestResultsColumnDefinition[] = [
  {
    id: 'created',
    label: 'Created',
    render: (item, ctx) =>
      formatInTimezone(item.created_at, ctx.timezone, ctx.timeDisplayFormat),
  },
  {
    id: 'status',
    label: 'Status',
    render: (item) => <BacktestStatusChip status={item.status} />,
  },
  {
    id: 'report',
    label: 'Report',
    render: (item) =>
      item.report_status ? <ReportStatusChip status={item.report_status} /> : '—',
  },
  {
    id: 'date_range',
    label: 'Date range',
    render: (item) =>
      item.selection
        ? `${item.selection.start_date} → ${item.selection.end_date}`
        : '—',
  },
  {
    id: 'universe',
    label: 'Universe',
    render: (item) => formatSelectionCounts(item.selection),
  },
  {
    id: 'runs',
    label: 'Runs',
    minWidth: 160,
    render: (item) => {
      const isActive = item.status === 'pending' || item.status === 'running'
      const progressValue =
        item.total_runs === 0 ? 0 : (item.completed_runs / item.total_runs) * 100

      if (!isActive) {
        return `${item.completed_runs}/${item.total_runs}`
      }

      return (
        <Stack spacing={0.75}>
          <Typography variant="body2" color="text.secondary">
            {item.completed_runs}/{item.total_runs}
          </Typography>
          <LinearProgress
            variant={item.total_runs === 0 ? 'indeterminate' : 'determinate'}
            value={progressValue}
            color="primary"
            sx={{
              height: 8,
              borderRadius: 1,
              bgcolor: 'action.hover',
              '& .MuiLinearProgress-bar': {
                borderRadius: 1,
              },
            }}
          />
        </Stack>
      )
    },
  },
  {
    id: 'runtime',
    label: 'Runtime',
    render: (item, ctx) => formatBacktestWallRuntime(item, ctx.nowMs),
  },
  {
    id: 'json',
    label: 'JSON',
    render: (item) =>
      item.status === 'completed' ? (
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
      ),
  },
  {
    id: 'yaml',
    label: 'YAML',
    render: (item) =>
      item.status === 'completed' ? (
        <Link
          href={backtestConfigUrl(item.id)}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          {item.id.slice(0, 8)}.yaml
        </Link>
      ) : (
        '—'
      ),
  },
]

const columnById = new Map(BACKTEST_RESULTS_COLUMNS.map((column) => [column.id, column]))

export function resolveVisibleColumns(
  preferences: readonly string[] | undefined,
): BacktestResultsColumnDefinition[] {
  const requested = (preferences?.length ? preferences : DEFAULT_BACKTEST_RESULTS_TABLE_COLUMNS).filter(
    (columnId): columnId is BacktestResultsColumnId =>
      BACKTEST_RESULTS_COLUMN_IDS.includes(columnId as BacktestResultsColumnId),
  )

  return requested
    .map((columnId) => columnById.get(columnId))
    .filter((column): column is BacktestResultsColumnDefinition => column !== undefined)
}
