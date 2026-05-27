import type {
  BacktestRunResult,
  BacktestRunSummary,
  CandidateDiagnostics,
  FilterDiagnostics,
  HistogramBin,
  RiskMetrics,
  TradeDiagnostics,
  TradeDistribution,
} from '../types/backtests'

const HOLD_TIME_BINS: Array<{ start: number; end: number; label: string }> = [
  { start: 0, end: 5, label: '0–5 min' },
  { start: 5, end: 15, label: '5–15 min' },
  { start: 15, end: 30, label: '15–30 min' },
  { start: 30, end: 60, label: '30–60 min' },
  { start: 60, end: Number.POSITIVE_INFINITY, label: '60+ min' },
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

function countInBins(values: number[], edges: typeof HOLD_TIME_BINS): HistogramBin[] {
  return edges.map(({ start, end, label }) => ({
    start,
    end: Number.isFinite(end) ? end : start,
    label,
    count: values.filter((value) => value >= start && value < end).length,
  }))
}

function sizeBins(values: number[]): HistogramBin[] {
  if (values.length === 0) {
    return []
  }
  const unique = [...new Set(values)].sort((left, right) => left - right)
  if (unique.length === 1) {
    return [{ start: unique[0], end: unique[0], count: values.length, label: String(unique[0]) }]
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const binCount = Math.min(6, Math.max(2, unique.length))
  const width = (max - min) / binCount
  const bins: HistogramBin[] = []
  for (let index = 0; index < binCount; index += 1) {
    const start = min + index * width
    const end = index === binCount - 1 ? Number.POSITIVE_INFINITY : min + (index + 1) * width
    const count =
      index === binCount - 1
        ? values.filter((value) => value >= start).length
        : values.filter((value) => value >= start && value < end).length
    bins.push({
      start,
      end: Number.isFinite(end) ? end : start,
      count,
      label: index === binCount - 1 ? `${start.toFixed(2)}+` : `${start.toFixed(2)}–${end.toFixed(2)}`,
    })
  }
  return bins
}

function median(values: number[]): number | null {
  if (values.length === 0) {
    return null
  }
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2
  }
  return sorted[middle]
}

function deriveTradeDiagnostics(result: BacktestRunResult, summary: BacktestRunSummary): TradeDiagnostics {
  const netPnls = result.trades.map((trade) => trade.pnlcomm)
  const grossPnls = result.trades.map((trade) => trade.pnl)
  const wins = netPnls.filter((value) => value > 0)
  const losses = netPnls.filter((value) => value <= 0)
  const grossPnl = grossPnls.reduce((sum, value) => sum + value, 0)
  const totalCommission = result.orders.reduce((sum, order) => sum + order.commission, 0)
  const netPnl = summary.end_value - summary.start_value
  const lossTotal = Math.abs(losses.reduce((sum, value) => sum + value, 0))

  const exitReasonCounts: Record<string, number> = {}
  const exitReasonPnl: Record<string, number> = {}
  for (const trade of result.trades) {
    const reason = trade.reason ?? 'unknown'
    exitReasonCounts[reason] = (exitReasonCounts[reason] ?? 0) + 1
    exitReasonPnl[reason] = (exitReasonPnl[reason] ?? 0) + trade.pnlcomm
  }

  const holdMinutes = result.trades
    .map((trade) => trade.hold_minutes)
    .filter((value): value is number => value != null)
  const sizes = result.trades.map((trade) => Math.abs(trade.size))
  const distributions: TradeDistribution = {
    hold_time_bins: countInBins(holdMinutes, HOLD_TIME_BINS),
    hold_time_unit: 'minutes',
    size_bins: sizeBins(sizes),
    size_value_bins: sizeBins(result.trades.map((trade) => Math.abs(trade.value))),
  }

  const dominantExitReason =
    Object.entries(exitReasonCounts).sort((left, right) => right[1] - left[1])[0]?.[0] ?? null

  return {
    net_pnl: netPnl,
    gross_pnl: grossPnl,
    total_commission: totalCommission,
    commission_pct_of_gross: grossPnl > 0 ? (totalCommission / grossPnl) * 100 : null,
    profit_factor: lossTotal > 0 ? wins.reduce((sum, value) => sum + value, 0) / lossTotal : null,
    expectancy: netPnls.length > 0 ? netPnls.reduce((sum, value) => sum + value, 0) / netPnls.length : null,
    avg_win: wins.length > 0 ? wins.reduce((sum, value) => sum + value, 0) / wins.length : null,
    avg_loss: losses.length > 0 ? losses.reduce((sum, value) => sum + value, 0) / losses.length : null,
    payoff_ratio:
      wins.length > 0 && losses.length > 0
        ? wins.reduce((sum, value) => sum + value, 0) /
          wins.length /
          Math.abs(losses.reduce((sum, value) => sum + value, 0) / losses.length)
        : null,
    win_rate_pct: netPnls.length > 0 ? (wins.length / netPnls.length) * 100 : null,
    median_hold_minutes: median(holdMinutes),
    mean_hold_minutes:
      holdMinutes.length > 0 ? holdMinutes.reduce((sum, value) => sum + value, 0) / holdMinutes.length : null,
    best_trade_pnl: netPnls.length > 0 ? Math.max(...netPnls) : null,
    worst_trade_pnl: netPnls.length > 0 ? Math.min(...netPnls) : null,
    exit_reason_counts: exitReasonCounts,
    exit_reason_pnl: exitReasonPnl,
    dominant_exit_reason: dominantExitReason,
    distributions,
  }
}

function parseTradeDiagnostics(value: unknown): TradeDiagnostics | null {
  if (!isRecord(value)) {
    return null
  }
  if (typeof value.net_pnl !== 'number' && typeof value.gross_pnl !== 'number') {
    return null
  }
  return value as unknown as TradeDiagnostics
}

function parseFilterDiagnostics(value: unknown): FilterDiagnostics | null {
  if (!isRecord(value)) {
    return null
  }
  if ('rejection_counts' in value) {
    return value as unknown as FilterDiagnostics
  }
  if ('filters' in value && isRecord(value.filters)) {
    return parseFilterDiagnostics(value.filters)
  }
  return null
}

function parseRiskMetrics(value: unknown): RiskMetrics | null {
  if (!isRecord(value)) {
    return null
  }
  return value as unknown as RiskMetrics
}

function deriveFilterDiagnostics(result: BacktestRunResult): FilterDiagnostics {
  const rejectionCounts: Record<string, number> = {}
  for (const rejection of result.rejections ?? []) {
    const reason = rejection.reason ?? 'unknown'
    rejectionCounts[reason] = (rejectionCounts[reason] ?? 0) + 1
  }
  const totalRejections = Object.values(rejectionCounts).reduce((sum, count) => sum + count, 0)
  const totalTrades = result.summary?.total_trades ?? result.trades.length
  const opportunities = totalTrades + totalRejections
  return {
    rejection_counts: rejectionCounts,
    total_rejections: totalRejections,
    signal_to_trade_pct: opportunities > 0 ? (totalTrades / opportunities) * 100 : null,
  }
}

export interface ResolvedRunDiagnostics {
  tradeDiagnostics: TradeDiagnostics | null
  filterDiagnostics: FilterDiagnostics | null
  riskMetrics: RiskMetrics | null
  candidateDiagnostics: CandidateDiagnostics | null
  includeCandidateLog: boolean
  isDerived: boolean
}

function parseCandidateDiagnostics(value: unknown): CandidateDiagnostics | null {
  if (!isRecord(value)) {
    return null
  }
  const { total_candidates, traded_candidates, rejected_candidates } = value
  if (
    typeof total_candidates !== 'number' ||
    typeof traded_candidates !== 'number' ||
    typeof rejected_candidates !== 'number'
  ) {
    return null
  }
  return { total_candidates, traded_candidates, rejected_candidates }
}

function deriveCandidateDiagnostics(result: BacktestRunResult): CandidateDiagnostics | null {
  const candidates = result.candidates ?? []
  if (candidates.length === 0) {
    return null
  }
  const traded = candidates.filter((candidate) => candidate.was_traded).length
  return {
    total_candidates: candidates.length,
    traded_candidates: traded,
    rejected_candidates: candidates.length - traded,
  }
}

export function resolveRunDiagnostics(result: BacktestRunResult): ResolvedRunDiagnostics {
  const summary = result.summary
  const includeCandidateLog = result.analyzers.include_candidate_log === true
  const candidateDiagnostics =
    parseCandidateDiagnostics(result.analyzers.candidate_diagnostics) ??
    deriveCandidateDiagnostics(result)
  if (!summary) {
    return {
      tradeDiagnostics: null,
      filterDiagnostics: null,
      riskMetrics: null,
      candidateDiagnostics,
      includeCandidateLog,
      isDerived: false,
    }
  }

  const summaryTrade = summary.trade_diagnostics ?? null
  const analyzerTrade = parseTradeDiagnostics(result.analyzers.trade_diagnostics)
  const tradeDiagnostics = summaryTrade ?? analyzerTrade

  const filterDiagnostics =
    summary.filter_diagnostics ??
    parseFilterDiagnostics(result.analyzers.filter_diagnostics) ??
    parseFilterDiagnostics(result.analyzers.filters)

  const riskMetrics =
    summary.risk_metrics ?? parseRiskMetrics(result.analyzers.risk_metrics)

  if (tradeDiagnostics) {
    return {
      tradeDiagnostics,
      filterDiagnostics: filterDiagnostics ?? deriveFilterDiagnostics(result),
      riskMetrics,
      candidateDiagnostics,
      includeCandidateLog,
      isDerived: false,
    }
  }

  if (result.trades.length === 0 && summary.total_trades === 0) {
    return {
      tradeDiagnostics: null,
      filterDiagnostics: filterDiagnostics ?? deriveFilterDiagnostics(result),
      riskMetrics,
      candidateDiagnostics,
      includeCandidateLog,
      isDerived: false,
    }
  }

  return {
    tradeDiagnostics: deriveTradeDiagnostics(result, summary),
    filterDiagnostics: filterDiagnostics ?? deriveFilterDiagnostics(result),
    riskMetrics,
    candidateDiagnostics,
    includeCandidateLog,
    isDerived: true,
  }
}
