import {
  Box,
  Chip,
  Paper,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material'
import { useMemo, useState } from 'react'

import type { BacktestRunResult, ReportAggregates, StrategyAggregate } from '../types/backtests'
import type { ComparisonViewMode } from '../utils/backtestAggregates'
import { formatSignedPercent } from '../utils/backtestAggregates'
import { BacktestStatusChip } from './BacktestStatusChip'

type SortKey = 'label' | 'return_pct' | 'sharpe_ratio' | 'max_drawdown_pct' | 'total_trades' | 'status'
type SortDirection = 'asc' | 'desc'

export type ComparisonRow =
  | { kind: 'run'; id: string; run: BacktestRunResult }
  | { kind: 'strategy'; id: string; aggregate: StrategyAggregate }

interface BacktestRunsComparisonTableProps {
  viewMode: ComparisonViewMode
  onViewModeChange: (mode: ComparisonViewMode) => void
  results: BacktestRunResult[]
  aggregates: ReportAggregates
  selectedRowId: string | null
  onSelectRow: (rowId: string | null) => void
}

function compareRows(left: ComparisonRow, right: ComparisonRow, sortKey: SortKey, direction: SortDirection): number {
  const factor = direction === 'asc' ? 1 : -1

  const read = (row: ComparisonRow) => {
    if (row.kind === 'run') {
      const summary = row.run.summary
      switch (sortKey) {
        case 'label':
          return `${row.run.symbol ?? ''}:${row.run.strategy}`
        case 'return_pct':
          return summary?.return_pct ?? Number.NEGATIVE_INFINITY
        case 'sharpe_ratio':
          return summary?.sharpe_ratio ?? Number.NEGATIVE_INFINITY
        case 'max_drawdown_pct':
          return summary?.max_drawdown_pct ?? Number.NEGATIVE_INFINITY
        case 'total_trades':
          return summary?.total_trades ?? -1
        case 'status':
          return row.run.status
        default:
          return ''
      }
    }

    const summary = row.aggregate.summary
    switch (sortKey) {
      case 'label':
        return row.aggregate.strategy
      case 'return_pct':
        return summary.return_pct
      case 'sharpe_ratio':
        return summary.sharpe_ratio ?? Number.NEGATIVE_INFINITY
      case 'max_drawdown_pct':
        return summary.max_drawdown_pct ?? Number.NEGATIVE_INFINITY
      case 'total_trades':
        return summary.total_trades
      case 'status':
        return row.aggregate.failed_runs > 0 ? 'failed' : 'success'
      default:
        return ''
    }
  }

  const leftValue = read(left)
  const rightValue = read(right)
  if (typeof leftValue === 'string' && typeof rightValue === 'string') {
    return leftValue.localeCompare(rightValue) * factor
  }
  return ((leftValue as number) - (rightValue as number)) * factor
}

export function BacktestRunsComparisonTable({
  viewMode,
  onViewModeChange,
  results,
  aggregates,
  selectedRowId,
  onSelectRow,
}: BacktestRunsComparisonTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('return_pct')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const rows = useMemo(() => {
    if (viewMode === 'strategy') {
      return aggregates.by_strategy.map(
        (aggregate): ComparisonRow => ({
          kind: 'strategy',
          id: aggregate.strategy,
          aggregate,
        }),
      )
    }
    return results.map(
      (run): ComparisonRow => ({
        kind: 'run',
        id: run.run_id,
        run,
      }),
    )
  }, [aggregates.by_strategy, results, viewMode])

  const sortedRows = useMemo(
    () => [...rows].sort((left, right) => compareRows(left, right, sortKey, sortDirection)),
    [rows, sortDirection, sortKey],
  )

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setSortDirection(key === 'label' ? 'asc' : 'desc')
  }

  return (
    <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{
          px: 2,
          py: 1.5,
          alignItems: { sm: 'center' },
          justifyContent: 'space-between',
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: 'action.hover',
        }}
      >
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Run comparison
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Click a row to expand analysis below the table.
          </Typography>
        </Box>
        <Tabs
          value={viewMode}
          onChange={(_, value: ComparisonViewMode) => {
            onViewModeChange(value)
            onSelectRow(null)
          }}
          aria-label="Comparison view mode"
        >
          <Tab value="symbol" label="Per symbol" />
          <Tab value="strategy" label="Merged by strategy" />
        </Tabs>
      </Stack>

      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sortDirection={sortKey === 'label' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'label'}
                  direction={sortKey === 'label' ? sortDirection : 'asc'}
                  onClick={() => handleSort('label')}
                >
                  {viewMode === 'strategy' ? 'Strategy' : 'Symbol / strategy'}
                </TableSortLabel>
              </TableCell>
              {viewMode === 'strategy' && <TableCell>Symbols</TableCell>}
              <TableCell align="right" sortDirection={sortKey === 'return_pct' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'return_pct'}
                  direction={sortKey === 'return_pct' ? sortDirection : 'desc'}
                  onClick={() => handleSort('return_pct')}
                >
                  Return
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={sortKey === 'sharpe_ratio' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'sharpe_ratio'}
                  direction={sortKey === 'sharpe_ratio' ? sortDirection : 'desc'}
                  onClick={() => handleSort('sharpe_ratio')}
                >
                  Sharpe
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={sortKey === 'max_drawdown_pct' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'max_drawdown_pct'}
                  direction={sortKey === 'max_drawdown_pct' ? sortDirection : 'desc'}
                  onClick={() => handleSort('max_drawdown_pct')}
                >
                  Max DD
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={sortKey === 'total_trades' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'total_trades'}
                  direction={sortKey === 'total_trades' ? sortDirection : 'desc'}
                  onClick={() => handleSort('total_trades')}
                >
                  Trades
                </TableSortLabel>
              </TableCell>
              <TableCell sortDirection={sortKey === 'status' ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === 'status'}
                  direction={sortKey === 'status' ? sortDirection : 'asc'}
                  onClick={() => handleSort('status')}
                >
                  Status
                </TableSortLabel>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedRows.map((row) => {
              const selected = selectedRowId === row.id
              if (row.kind === 'run') {
                const summary = row.run.summary
                return (
                  <TableRow
                    key={row.id}
                    hover
                    selected={selected}
                    onClick={() => onSelectRow(selected ? null : row.id)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {row.run.symbol ?? 'Unknown'} / {row.run.strategy}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{formatSignedPercent(summary?.return_pct)}</TableCell>
                    <TableCell align="right">{summary?.sharpe_ratio?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell align="right">{formatSignedPercent(summary?.max_drawdown_pct)}</TableCell>
                    <TableCell align="right">{summary?.total_trades ?? '—'}</TableCell>
                    <TableCell>
                      <BacktestStatusChip status={row.run.status === 'success' ? 'completed' : 'failed'} />
                    </TableCell>
                  </TableRow>
                )
              }

              const summary = row.aggregate.summary
              const status =
                row.aggregate.failed_runs > 0
                  ? row.aggregate.successful_runs > 0
                    ? 'partial'
                    : 'failed'
                  : 'completed'
              return (
                <TableRow
                  key={row.id}
                  hover
                  selected={selected}
                  onClick={() => onSelectRow(selected ? null : row.id)}
                  sx={{ cursor: 'pointer' }}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {row.aggregate.strategy}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {row.aggregate.successful_runs} successful · {row.aggregate.failed_runs} failed
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
                      {row.aggregate.symbols.map((symbol) => (
                        <Chip key={symbol} label={symbol} size="small" variant="outlined" />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">{formatSignedPercent(summary.return_pct)}</TableCell>
                  <TableCell align="right">{summary.sharpe_ratio?.toFixed(2) ?? '—'}</TableCell>
                  <TableCell align="right">{formatSignedPercent(summary.max_drawdown_pct)}</TableCell>
                  <TableCell align="right">{summary.total_trades}</TableCell>
                  <TableCell>
                    {status === 'partial' ? (
                      <Chip label="Partial" size="small" color="warning" variant="outlined" />
                    ) : (
                      <BacktestStatusChip status={status} />
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Box>
    </Paper>
  )
}
