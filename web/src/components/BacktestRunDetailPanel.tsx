import {
  Alert,
  Box,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import dayjs from 'dayjs'
import { useState } from 'react'

import type { BacktestRunResult, BacktestSelectionSummary } from '../types/backtests'
import { resolveRunDiagnostics } from '../utils/backtestDiagnostics'
import { formatInTimezone } from '../utils/datetime'
import { BacktestAnalysisSection } from './BacktestAnalysisSection'
import { BacktestTradeRecordsTable } from './BacktestTradeRecordsTable'
import {
  DiagnosticsLayout,
  FilterDiagnosticsPanel,
  HeadlineMetricsGrid,
  RiskMetricsPanel,
  TradeDiagnosticsPanel,
} from './BacktestDiagnosticsPanels'
import { DiagnosticsTableShell } from './BacktestMetricGrid'
import { BacktestRunChart } from './BacktestRunChart'
import { TradeDistributionCharts } from './TradeDistributionCharts'
import { useSettings } from '../settings/useSettings'
import { buildTradeChartFocusWindowMs, type TradeChartFocusWindowMs } from '../utils/backtestChartFocus'

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

function medianTradeSize(trades: BacktestRunResult['trades']): number | null {
  if (trades.length === 0) {
    return null
  }
  const sizes = [...trades.map((trade) => Math.abs(trade.size))].sort((left, right) => left - right)
  const middle = Math.floor(sizes.length / 2)
  if (sizes.length % 2 === 0) {
    return (sizes[middle - 1] + sizes[middle]) / 2
  }
  return sizes[middle]
}

interface BacktestRunDetailPanelProps {
  backtestId: string
  result: BacktestRunResult
  selection: BacktestSelectionSummary | null
}

export function BacktestRunDetailPanel({ backtestId, result, selection }: BacktestRunDetailPanelProps) {
  const { platformSettings, appearance } = useSettings()
  const [tab, setTab] = useState<'overview' | 'chart' | 'diagnostics' | 'candidates' | 'trades'>('overview')
  const [chartFocusWindow, setChartFocusWindow] = useState<TradeChartFocusWindowMs | null>(null)
  const summary = result.summary
  const resolved = resolveRunDiagnostics(result)
  const tradeDiagnostics = resolved.tradeDiagnostics
  const filterDiagnostics = resolved.filterDiagnostics
  const riskMetrics = resolved.riskMetrics
  const candidateDiagnostics = resolved.candidateDiagnostics
  const includeCandidateLog = resolved.includeCandidateLog
  const candidateRecordsMissing = resolved.candidateRecordsMissing
  const distributions = tradeDiagnostics?.distributions ?? null
  const candidates = result.candidates ?? []
  const candidateCount = candidateDiagnostics?.total_candidates ?? candidates.length

  const sortedTrades = [...result.trades].sort((left, right) => {
    const leftValue = left.datetime ? dayjs(left.datetime).valueOf() : Number.NEGATIVE_INFINITY
    const rightValue = right.datetime ? dayjs(right.datetime).valueOf() : Number.NEGATIVE_INFINITY
    return leftValue - rightValue
  })
  const sortedOrders = [...result.orders].sort((left, right) => {
    const leftValue = left.datetime ? dayjs(left.datetime).valueOf() : Number.NEGATIVE_INFINITY
    const rightValue = right.datetime ? dayjs(right.datetime).valueOf() : Number.NEGATIVE_INFINITY
    return leftValue - rightValue
  })
  const firstTrade = sortedTrades[0] ?? null
  const lastTrade = sortedTrades.at(-1) ?? null
  const latestOrders = [...sortedOrders].reverse().slice(0, 5)

  const handleFocusChartTrade = (trade: BacktestRunResult['trades'][number]) => {
    const focusWindow = buildTradeChartFocusWindowMs(trade)
    if (!focusWindow) {
      return
    }

    setChartFocusWindow(focusWindow)
    setTab('chart')
  }

  return (
    <Box sx={{ borderTop: 1, borderColor: 'divider', bgcolor: 'background.default' }}>
      <Stack spacing={2} sx={{ p: 2 }}>
        <Stack spacing={0.5}>
          <Typography variant="h6">
            {result.symbol ?? 'Unknown symbol'} / {result.strategy}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {result.name ?? result.run_id}
          </Typography>
        </Stack>

        {result.error && <Alert severity="error">{result.error.message}</Alert>}
        {resolved.isDerived && (
          <Alert severity="info">
            Some metrics were computed in the browser from trade records. Re-run this backtest to persist full
            diagnostics in the stored artifacts.
          </Alert>
        )}

        <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label="Run analysis sections">
          <Tab value="overview" label="Overview" />
          <Tab
            value="chart"
            label="Chart"
            disabled={result.status !== 'success' || !result.symbol || !selection}
          />
          <Tab value="diagnostics" label="Diagnostics" />
          <Tab
            value="candidates"
            label={includeCandidateLog ? `Candidates (${candidateCount})` : 'Candidates'}
          />
          <Tab value="trades" label={`Trades (${result.trades.length})`} />
        </Tabs>

        {tab === 'overview' && summary && (
          <BacktestAnalysisSection title="Overview" description="Headline performance for this symbol and strategy.">
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

        {tab === 'chart' && result.status === 'success' && result.symbol && selection && (
          <BacktestAnalysisSection title="Price chart" description="Market bars with order and trade markers.">
            <BacktestRunChart
              key={result.run_id}
              symbol={result.symbol}
              startDate={selection.start_date}
              endDate={selection.end_date}
              resolution={selection.resolution}
              orders={result.orders}
              trades={result.trades}
              focusWindow={chartFocusWindow}
              onResetFocusWindow={() => setChartFocusWindow(null)}
            />
          </BacktestAnalysisSection>
        )}

        {tab === 'diagnostics' && (tradeDiagnostics || filterDiagnostics || riskMetrics) && (
          <BacktestAnalysisSection
            title="Strategy diagnostics"
            description="Trade economics, distributions, filters, and risk context."
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
                      medianSize={medianTradeSize(result.trades)}
                    />
                  </Box>
                )}
                {filterDiagnostics && <FilterDiagnosticsPanel diagnostics={filterDiagnostics} />}
                {riskMetrics && <RiskMetricsPanel metrics={riskMetrics} />}
              </DiagnosticsLayout>
            </Stack>
          </BacktestAnalysisSection>
        )}

        {tab === 'candidates' && (
          <BacktestAnalysisSection
            title="Entry candidates"
            description="Signals evaluated for entry, including rejected opportunities when candidate logging is enabled."
          >
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Typography variant="subtitle1">Candidate log</Typography>
                <Chip
                  size="small"
                  label={includeCandidateLog ? 'enabled' : 'disabled'}
                  color={includeCandidateLog ? 'primary' : 'default'}
                />
              </Stack>
              {!includeCandidateLog ? (
                <Alert severity="info">
                  Candidate logging was not enabled for this run. Turn on{' '}
                  <strong>Include candidate log</strong> in Settings → Backtest defaults or in the backtest
                  wizard before submitting to record entry candidates.
                </Alert>
              ) : (
                <>
                  {candidateRecordsMissing && (
                    <Alert severity="warning">
                      This run recorded {candidateDiagnostics?.total_candidates ?? 0} candidates, but the
                      detailed records could not be loaded. Re-open this backtest detail page or re-run the
                      backtest if the issue persists.
                    </Alert>
                  )}
                  {candidateDiagnostics ? (
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
                      <Metric label="Total candidates" value={String(candidateDiagnostics.total_candidates)} />
                      <Metric label="Traded" value={String(candidateDiagnostics.traded_candidates)} />
                      <Metric label="Rejected" value={String(candidateDiagnostics.rejected_candidates)} />
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Candidate logging was enabled but no candidates were recorded for this run.
                    </Typography>
                  )}
                  {candidates.length > 0 ? (
                    <DiagnosticsTableShell title={`Candidate records (${candidates.length})`}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>When</TableCell>
                            <TableCell>Symbol</TableCell>
                            <TableCell align="right">Signal</TableCell>
                            <TableCell>Traded</TableCell>
                            <TableCell>Reject reason</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {candidates.map((candidate) => (
                            <TableRow key={candidate.candidate_id} hover>
                              <TableCell>
                                {formatTimestampOrDash(
                                  candidate.timestamp,
                                  platformSettings.platform_behavior.timezone,
                                  appearance.time_display_format,
                                )}
                              </TableCell>
                              <TableCell>{candidate.symbol}</TableCell>
                              <TableCell align="right">
                                {formatNumber(candidate.signal_score, 2)}
                              </TableCell>
                              <TableCell>{candidate.was_traded ? 'yes' : 'no'}</TableCell>
                              <TableCell>{candidate.reject_reason ?? '—'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </DiagnosticsTableShell>
                  ) : (
                    !candidateRecordsMissing &&
                    candidateDiagnostics &&
                    candidateDiagnostics.total_candidates === 0 && (
                      <Typography variant="body2" color="text.secondary">
                        No entry candidates were emitted for this run.
                      </Typography>
                    )
                  )}
                </>
              )}
            </Stack>
          </BacktestAnalysisSection>
        )}

        {tab === 'trades' && (
          <BacktestAnalysisSection title="Trade activity" description="Execution summary and detailed trade records.">
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                <Metric label="Orders" value={String(result.orders.length)} />
                <Metric label="Trade records" value={String(result.trades.length)} />
                <Metric
                  label="First trade"
                  value={formatTimestampOrDash(
                    firstTrade?.datetime,
                    platformSettings.platform_behavior.timezone,
                    appearance.time_display_format,
                  )}
                />
                <Metric
                  label="Last trade"
                  value={formatTimestampOrDash(
                    lastTrade?.datetime,
                    platformSettings.platform_behavior.timezone,
                    appearance.time_display_format,
                  )}
                />
                <Metric label="Data source" value={result.data_source} />
              </Stack>

              <DiagnosticsTableShell title={`Trade records (${result.trades.length})`}>
                <BacktestTradeRecordsTable
                  backtestId={backtestId}
                  runId={result.run_id}
                  trades={result.trades}
                  timezone={platformSettings.platform_behavior.timezone}
                  timeDisplayFormat={appearance.time_display_format}
                  onFocusChartTrade={handleFocusChartTrade}
                />
              </DiagnosticsTableShell>

              {latestOrders.length > 0 && (
                <DiagnosticsTableShell title={`Recent orders (${latestOrders.length})`}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>When</TableCell>
                        <TableCell>Side</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell align="right">Size</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Value</TableCell>
                        <TableCell align="right">Commission</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {latestOrders.map((order, index) => (
                        <TableRow key={`${order.datetime ?? 'no-datetime'}-${order.status}-${index}`} hover>
                          <TableCell>
                            {formatTimestampOrDash(
                              order.datetime,
                              platformSettings.platform_behavior.timezone,
                              appearance.time_display_format,
                            )}
                          </TableCell>
                          <TableCell>{order.is_buy ? 'Buy' : 'Sell'}</TableCell>
                          <TableCell>{order.status}</TableCell>
                          <TableCell align="right">{formatNumber(order.size, 2)}</TableCell>
                          <TableCell align="right">{formatNumber(order.price, 2)}</TableCell>
                          <TableCell align="right">{formatNumber(order.value, 2)}</TableCell>
                          <TableCell align="right">{formatNumber(order.commission, 2)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </DiagnosticsTableShell>
              )}
            </Stack>
          </BacktestAnalysisSection>
        )}
      </Stack>
    </Box>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {label}
      </Typography>
      <Typography>{value}</Typography>
    </Box>
  )
}
