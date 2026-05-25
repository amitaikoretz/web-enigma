import {
  Box,
  Chip,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import type { ReactNode } from 'react'

import type { FilterDiagnostics, RiskMetrics, TradeDiagnostics } from '../types/backtests'
import {
  DiagnosticsTableShell,
  MetricGrid,
  formatMetricNumber,
  formatMetricPercent,
  formatSignedPercent,
  pnlTone,
  type MetricItem,
} from './BacktestMetricGrid'

function buildTradeEconomicsMetrics(diagnostics: TradeDiagnostics): MetricItem[] {
  return [
    { label: 'Net PnL', value: formatMetricNumber(diagnostics.net_pnl), tone: pnlTone(diagnostics.net_pnl) },
    { label: 'Gross PnL', value: formatMetricNumber(diagnostics.gross_pnl), tone: pnlTone(diagnostics.gross_pnl) },
    { label: 'Commission', value: formatMetricNumber(diagnostics.total_commission) },
    { label: 'Commission / gross', value: formatMetricPercent(diagnostics.commission_pct_of_gross) },
    { label: 'Profit factor', value: formatMetricNumber(diagnostics.profit_factor, 3) },
    { label: 'Expectancy', value: formatMetricNumber(diagnostics.expectancy), tone: pnlTone(diagnostics.expectancy) },
    { label: 'Win rate', value: formatMetricPercent(diagnostics.win_rate_pct) },
    { label: 'Payoff ratio', value: formatMetricNumber(diagnostics.payoff_ratio, 3) },
    {
      label: 'Avg win / loss',
      value: `${formatMetricNumber(diagnostics.avg_win)} / ${formatMetricNumber(diagnostics.avg_loss)}`,
    },
    {
      label: 'Best / worst trade',
      value: `${formatMetricNumber(diagnostics.best_trade_pnl)} / ${formatMetricNumber(diagnostics.worst_trade_pnl)}`,
    },
    {
      label: 'Median hold',
      value:
        diagnostics.median_hold_minutes != null
          ? `${formatMetricNumber(diagnostics.median_hold_minutes, 1)} min`
          : '—',
    },
  ]
}

function buildRiskMetrics(diagnostics: RiskMetrics): MetricItem[] {
  return [
    { label: 'Sortino', value: formatMetricNumber(diagnostics.sortino_ratio, 3) },
    { label: 'Calmar', value: formatMetricNumber(diagnostics.calmar_ratio, 3) },
    { label: 'Buy & hold', value: formatSignedPercent(diagnostics.buy_hold_return_pct) },
    {
      label: 'Alpha vs B&H',
      value: formatSignedPercent(diagnostics.alpha_vs_buy_hold_pct),
      tone: pnlTone(diagnostics.alpha_vs_buy_hold_pct),
    },
    { label: 'Exposure time', value: formatMetricPercent(diagnostics.exposure_time_pct) },
    { label: 'Avg drawdown', value: formatSignedPercent(diagnostics.avg_drawdown_pct) },
    { label: 'Max DD duration', value: diagnostics.max_drawdown_duration ?? '—' },
  ]
}

export function TradeDiagnosticsPanel({ diagnostics }: { diagnostics: TradeDiagnostics }) {
  const exitReasons = Object.entries(diagnostics.exit_reason_counts).sort((left, right) => right[1] - left[1])

  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Trade economics
      </Typography>
      <MetricGrid items={buildTradeEconomicsMetrics(diagnostics)} minColumnWidth={140} />

      {exitReasons.length > 0 && (
        <DiagnosticsTableShell title="Exit reasons">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Reason</TableCell>
                <TableCell align="right">Count</TableCell>
                <TableCell align="right">Net PnL</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {exitReasons.map(([reason, count]) => {
                const pnl = diagnostics.exit_reason_pnl[reason]
                return (
                  <TableRow key={reason} hover>
                    <TableCell>
                      <Chip label={reason} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell align="right">{count}</TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        fontWeight: 600,
                        color: pnlTone(pnl) === 'positive' ? 'success.main' : pnlTone(pnl) === 'negative' ? 'error.main' : undefined,
                      }}
                    >
                      {formatMetricNumber(pnl)}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </DiagnosticsTableShell>
      )}
    </Stack>
  )
}

export function FilterDiagnosticsPanel({ diagnostics }: { diagnostics: FilterDiagnostics }) {
  const rejectionRows = Object.entries(diagnostics.rejection_counts).sort((left, right) => right[1] - left[1])
  const maxRejectionCount = rejectionRows[0]?.[1] ?? 0

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Filter funnel
      </Typography>
      <MetricGrid
        items={[
          { label: 'Rejections', value: String(diagnostics.total_rejections) },
          { label: 'Signal-to-trade', value: formatMetricPercent(diagnostics.signal_to_trade_pct) },
        ]}
        minColumnWidth={160}
      />

      {diagnostics.total_rejections === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No auditor rejections recorded for this run.
        </Typography>
      ) : (
        <DiagnosticsTableShell title="Rejection breakdown">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Reason</TableCell>
                <TableCell align="right">Count</TableCell>
                <TableCell sx={{ width: '42%' }}>Share</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rejectionRows.map(([reason, count]) => (
                <TableRow key={reason} hover>
                  <TableCell>
                    <Chip label={reason} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell align="right">{count}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                      <LinearProgress
                        variant="determinate"
                        value={maxRejectionCount > 0 ? (count / maxRejectionCount) * 100 : 0}
                        sx={{ flex: 1, height: 8, borderRadius: 999 }}
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 36, textAlign: 'right' }}>
                        {formatMetricPercent((count / diagnostics.total_rejections) * 100, 0)}
                      </Typography>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DiagnosticsTableShell>
      )}
    </Stack>
  )
}

export function RiskMetricsPanel({ metrics }: { metrics: RiskMetrics }) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Risk context
      </Typography>
      <MetricGrid items={buildRiskMetrics(metrics)} minColumnWidth={140} />
    </Stack>
  )
}

export function PortfolioSummaryPanel({
  summary,
}: {
  summary: import('../types/backtests').BacktestPortfolioSummary
}) {
  return (
    <MetricGrid
      items={[
        {
          label: 'Net PnL',
          value: formatMetricNumber(summary.total_net_pnl),
          tone: pnlTone(summary.total_net_pnl),
        },
        { label: 'Trades', value: String(summary.total_trades) },
        { label: 'Wins / losses', value: `${summary.won_trades} / ${summary.lost_trades}` },
        { label: 'Win rate', value: formatMetricPercent(summary.win_rate_pct) },
      ]}
      minColumnWidth={150}
    />
  )
}

export function HeadlineMetricsGrid({
  returnPct,
  sharpeRatio,
  maxDrawdownPct,
  totalTrades,
  wonTrades,
  lostTrades,
  winRatePct,
}: {
  returnPct: number
  sharpeRatio: number | null
  maxDrawdownPct: number | null
  totalTrades: number
  wonTrades: number
  lostTrades: number
  winRatePct: number | null | undefined
}) {
  return (
    <MetricGrid
      items={[
        { label: 'Return', value: formatSignedPercent(returnPct), tone: pnlTone(returnPct) },
        { label: 'Sharpe', value: sharpeRatio?.toFixed(2) ?? '—' },
        { label: 'Max drawdown', value: formatSignedPercent(maxDrawdownPct) },
        { label: 'Trades', value: String(totalTrades) },
        { label: 'Wins / losses', value: `${wonTrades} / ${lostTrades}` },
        { label: 'Win rate', value: formatMetricPercent(winRatePct ?? null) },
      ]}
      minColumnWidth={132}
    />
  )
}

export function DiagnosticsLayout({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
        gap: 2,
        alignItems: 'start',
      }}
    >
      {children}
    </Box>
  )
}
