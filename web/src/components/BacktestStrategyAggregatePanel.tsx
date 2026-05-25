import {
  Alert,
  Box,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import type { BacktestRunResult, StrategyAggregate } from '../types/backtests'
import { mergedTradesForStrategy } from '../utils/backtestAggregates'
import { formatInTimezone } from '../utils/datetime'
import { BacktestAnalysisSection } from './BacktestAnalysisSection'
import { BacktestEquityCurveChart } from './BacktestEquityCurveChart'
import {
  DiagnosticsLayout,
  FilterDiagnosticsPanel,
  HeadlineMetricsGrid,
  TradeDiagnosticsPanel,
} from './BacktestDiagnosticsPanels'
import { DiagnosticsTableShell } from './BacktestMetricGrid'
import { TradeDistributionCharts } from './TradeDistributionCharts'
import { useSettings } from '../settings/useSettings'

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toFixed(digits)
}

function formatTimestampOrDash(
  value: string | null | undefined,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  if (!value) {
    return '—'
  }
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

interface BacktestStrategyAggregatePanelProps {
  aggregate: StrategyAggregate
  results: BacktestRunResult[]
  missingMergedRiskMetrics: boolean
}

export function BacktestStrategyAggregatePanel({
  aggregate,
  results,
  missingMergedRiskMetrics,
}: BacktestStrategyAggregatePanelProps) {
  const { platformSettings, appearance } = useSettings()
  const [tab, setTab] = useState<'overview' | 'equity' | 'diagnostics' | 'trades'>('overview')
  const summary = aggregate.summary
  const tradeDiagnostics = summary.trade_diagnostics ?? null
  const filterDiagnostics = summary.filter_diagnostics ?? null
  const distributions = tradeDiagnostics?.distributions ?? null

  const mergedTrades = useMemo(
    () =>
      [...mergedTradesForStrategy(results, aggregate)].sort((left, right) => {
        const leftValue = left.datetime ? dayjs(left.datetime).valueOf() : Number.NEGATIVE_INFINITY
        const rightValue = right.datetime ? dayjs(right.datetime).valueOf() : Number.NEGATIVE_INFINITY
        return leftValue - rightValue
      }),
    [aggregate, results],
  )

  return (
    <Box sx={{ borderTop: 1, borderColor: 'divider', bgcolor: 'background.default' }}>
      <Stack spacing={2} sx={{ p: 2 }}>
        <Stack spacing={0.5}>
          <Typography variant="h6">{aggregate.strategy}</Typography>
          <Typography variant="body2" color="text.secondary">
            Merged across {aggregate.symbols.join(', ')} · {aggregate.successful_runs} successful run
            {aggregate.successful_runs === 1 ? '' : 's'}
          </Typography>
        </Stack>

        {missingMergedRiskMetrics && (
          <Alert severity="info">
            Merged Sharpe and max drawdown require equity curves in the report. Re-run this backtest to persist
            strategy-level risk metrics.
          </Alert>
        )}

        <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label="Strategy aggregate sections">
          <Tab value="overview" label="Overview" />
          <Tab value="equity" label="Equity" disabled={aggregate.equity_curve.length === 0} />
          <Tab value="diagnostics" label="Diagnostics" />
          <Tab value="trades" label={`Trades (${mergedTrades.length})`} />
        </Tabs>

        {tab === 'overview' && (
          <BacktestAnalysisSection
            title="Overview"
            description="Combined performance across all symbols for this strategy."
          >
            <HeadlineMetricsGrid
              returnPct={summary.return_pct}
              sharpeRatio={summary.sharpe_ratio}
              maxDrawdownPct={summary.max_drawdown_pct}
              totalTrades={summary.total_trades}
              wonTrades={summary.won_trades}
              lostTrades={summary.lost_trades}
              winRatePct={tradeDiagnostics?.win_rate_pct}
            />
          </BacktestAnalysisSection>
        )}

        {tab === 'equity' && (
          <BacktestAnalysisSection
            title="Merged equity curve"
            description="Combined equity from parallel equal-capital symbol runs."
          >
            <BacktestEquityCurveChart curve={aggregate.equity_curve} />
          </BacktestAnalysisSection>
        )}

        {tab === 'diagnostics' && (tradeDiagnostics || filterDiagnostics) && (
          <BacktestAnalysisSection
            title="Strategy diagnostics"
            description="Trade economics and filter activity aggregated across symbols."
          >
            <Stack spacing={2}>
              <DiagnosticsLayout>
                {tradeDiagnostics && (
                  <Box sx={{ gridColumn: { lg: '1 / -1' } }}>
                    <TradeDiagnosticsPanel diagnostics={tradeDiagnostics} />
                  </Box>
                )}
                {distributions && (
                  <Box sx={{ gridColumn: { lg: '1 / -1' } }}>
                    <TradeDistributionCharts
                      distributions={distributions}
                      medianHoldMinutes={tradeDiagnostics?.median_hold_minutes}
                      medianSize={null}
                    />
                  </Box>
                )}
                {filterDiagnostics && <FilterDiagnosticsPanel diagnostics={filterDiagnostics} />}
              </DiagnosticsLayout>
            </Stack>
          </BacktestAnalysisSection>
        )}

        {tab === 'trades' && (
          <BacktestAnalysisSection
            title="Merged trade activity"
            description="All trade records across symbols for this strategy."
          >
            {mergedTrades.length > 0 ? (
              <DiagnosticsTableShell title={`Trade records (${mergedTrades.length})`}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell>When</TableCell>
                      <TableCell align="right">Size</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">PnL after fees</TableCell>
                      <TableCell>Exit</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {mergedTrades.map((trade, index) => (
                      <TableRow key={`${trade.symbol ?? 'unknown'}-${trade.datetime ?? index}`} hover>
                        <TableCell>{trade.symbol ?? '—'}</TableCell>
                        <TableCell>
                          {formatTimestampOrDash(
                            trade.datetime,
                            platformSettings.platform_behavior.timezone,
                            appearance.time_display_format,
                          )}
                        </TableCell>
                        <TableCell align="right">{formatNumber(trade.size, 2)}</TableCell>
                        <TableCell align="right">{formatNumber(trade.price, 2)}</TableCell>
                        <TableCell align="right">{formatNumber(trade.pnlcomm, 2)}</TableCell>
                        <TableCell>{trade.reason ?? '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </DiagnosticsTableShell>
            ) : (
              <Typography color="text.secondary">No trade records were emitted for this strategy.</Typography>
            )}
          </BacktestAnalysisSection>
        )}
      </Stack>
    </Box>
  )
}
