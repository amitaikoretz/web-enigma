import type {
  BacktestPortfolioSummary,
  BacktestReport,
  BacktestRunResult,
  PortfolioAggregate,
  ReportAggregates,
  StrategyAggregate,
} from '../types/backtests'

export type ComparisonViewMode = 'symbol' | 'strategy'

export interface ResolvedReportAggregates {
  aggregates: ReportAggregates
  isDerived: boolean
  missingMergedRiskMetrics: boolean
}

function netPnlForRun(result: BacktestRunResult): number {
  const summary = result.summary
  if (!summary) {
    return 0
  }
  return summary.trade_diagnostics?.net_pnl ?? summary.end_value - summary.start_value
}

function computePortfolioFallback(results: BacktestRunResult[]): PortfolioAggregate | null {
  const successful = results.filter((result) => result.status === 'success' && result.summary)
  if (successful.length <= 1) {
    return null
  }

  let totalNetPnl = 0
  let totalTrades = 0
  let wonTrades = 0
  let lostTrades = 0
  let startValue = 0
  let endValue = 0
  let bestRunId: string | null = null
  let worstRunId: string | null = null
  let bestReturn: number | null = null
  let worstReturn: number | null = null

  for (const result of successful) {
    const summary = result.summary
    if (!summary) {
      continue
    }
    totalNetPnl += netPnlForRun(result)
    totalTrades += summary.total_trades
    wonTrades += summary.won_trades
    lostTrades += summary.lost_trades
    startValue += summary.start_value
    endValue += summary.end_value
    if (bestReturn === null || summary.return_pct > bestReturn) {
      bestReturn = summary.return_pct
      bestRunId = result.run_id
    }
    if (worstReturn === null || summary.return_pct < worstReturn) {
      worstReturn = summary.return_pct
      worstRunId = result.run_id
    }
  }

  return {
    total_net_pnl: totalNetPnl,
    total_trades: totalTrades,
    won_trades: wonTrades,
    lost_trades: lostTrades,
    win_rate_pct: totalTrades > 0 ? (wonTrades / totalTrades) * 100 : null,
    combined_return_pct: startValue > 0 ? ((endValue - startValue) / startValue) * 100 : null,
    best_run_id: bestRunId,
    worst_run_id: worstRunId,
  }
}

function computeStrategyFallback(results: BacktestRunResult[]): StrategyAggregate[] {
  const byStrategy = new Map<string, BacktestRunResult[]>()
  for (const result of results) {
    const group = byStrategy.get(result.strategy) ?? []
    group.push(result)
    byStrategy.set(result.strategy, group)
  }

  return [...byStrategy.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([strategy, runs]) => {
      const successful = runs.filter((run) => run.status === 'success' && run.summary)
      const failed = runs.filter((run) => run.status === 'failed')
      const symbols = [...new Set(runs.map((run) => run.symbol).filter(Boolean))] as string[]

      if (successful.length === 0) {
        return {
          strategy,
          symbols,
          run_ids: runs.map((run) => run.run_id),
          successful_runs: 0,
          failed_runs: failed.length,
          summary: {
            start_value: 0,
            end_value: 0,
            return_pct: 0,
            max_drawdown_pct: null,
            sharpe_ratio: null,
            total_trades: 0,
            won_trades: 0,
            lost_trades: 0,
          },
          equity_curve: [],
        }
      }

      const startValue = successful.reduce((sum, run) => sum + (run.summary?.start_value ?? 0), 0)
      const endValue = successful.reduce((sum, run) => sum + (run.summary?.end_value ?? 0), 0)
      const totalTrades = successful.reduce((sum, run) => sum + (run.summary?.total_trades ?? 0), 0)
      const wonTrades = successful.reduce((sum, run) => sum + (run.summary?.won_trades ?? 0), 0)
      const lostTrades = successful.reduce((sum, run) => sum + (run.summary?.lost_trades ?? 0), 0)
      const netPnl = successful.reduce((sum, run) => sum + netPnlForRun(run), 0)

      return {
        strategy,
        symbols: symbols.sort(),
        run_ids: runs.map((run) => run.run_id),
        successful_runs: successful.length,
        failed_runs: failed.length,
        summary: {
          start_value: startValue,
          end_value: endValue,
          return_pct: startValue > 0 ? ((endValue - startValue) / startValue) * 100 : 0,
          max_drawdown_pct: null,
          sharpe_ratio: null,
          total_trades: totalTrades,
          won_trades: wonTrades,
          lost_trades: lostTrades,
          trade_diagnostics: {
            net_pnl: netPnl,
            gross_pnl: netPnl,
            total_commission: 0,
            commission_pct_of_gross: null,
            profit_factor: null,
            expectancy: totalTrades > 0 ? netPnl / totalTrades : null,
            avg_win: null,
            avg_loss: null,
            payoff_ratio: null,
            win_rate_pct: totalTrades > 0 ? (wonTrades / totalTrades) * 100 : null,
            median_hold_minutes: null,
            mean_hold_minutes: null,
            best_trade_pnl: null,
            worst_trade_pnl: null,
            exit_reason_counts: {},
            exit_reason_pnl: {},
            dominant_exit_reason: null,
            distributions: null,
          },
        },
        equity_curve: [],
      }
    })
}

export function resolveReportAggregates(report: BacktestReport): ResolvedReportAggregates {
  if (report.aggregates) {
    const missingMergedRiskMetrics = report.aggregates.by_strategy.some(
      (aggregate) =>
        aggregate.successful_runs > 0 &&
        aggregate.equity_curve.length === 0 &&
        aggregate.summary.max_drawdown_pct == null &&
        aggregate.summary.sharpe_ratio == null,
    )
    return {
      aggregates: report.aggregates,
      isDerived: false,
      missingMergedRiskMetrics,
    }
  }

  return {
    aggregates: {
      portfolio: computePortfolioFallback(report.results),
      by_strategy: computeStrategyFallback(report.results),
    },
    isDerived: true,
    missingMergedRiskMetrics: true,
  }
}

export function portfolioSummaryFromAggregate(
  portfolio: PortfolioAggregate | null,
): BacktestPortfolioSummary | null {
  if (!portfolio) {
    return null
  }
  return {
    total_net_pnl: portfolio.total_net_pnl,
    total_trades: portfolio.total_trades,
    won_trades: portfolio.won_trades,
    lost_trades: portfolio.lost_trades,
    win_rate_pct: portfolio.win_rate_pct,
  }
}

export function findRunById(results: BacktestRunResult[], runId: string): BacktestRunResult | undefined {
  return results.find((result) => result.run_id === runId)
}

export function findStrategyAggregate(
  aggregates: ReportAggregates,
  strategy: string,
): StrategyAggregate | undefined {
  return aggregates.by_strategy.find((aggregate) => aggregate.strategy === strategy)
}

export function mergedTradesForStrategy(
  results: BacktestRunResult[],
  aggregate: StrategyAggregate,
): Array<BacktestRunResult['trades'][number] & { symbol: string | null }> {
  const runsById = new Map(results.map((result) => [result.run_id, result]))
  const merged: Array<BacktestRunResult['trades'][number] & { symbol: string | null }> = []

  for (const runId of aggregate.run_ids) {
    const run = runsById.get(runId)
    if (!run) {
      continue
    }
    for (const trade of run.trades) {
      merged.push({ ...trade, symbol: run.symbol })
    }
  }

  return merged
}

export function formatSignedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}
