export type BacktestJobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type BacktestReportStatus = 'success' | 'partial_failure' | 'failure'
export type BacktestFeed = 'iex' | 'sip' | 'otc'

export interface HistogramBin {
  start: number
  end: number
  count: number
  label: string | null
}

export interface TradeDistribution {
  hold_time_bins: HistogramBin[]
  hold_time_unit: 'minutes' | 'bars'
  size_bins: HistogramBin[]
  size_value_bins: HistogramBin[] | null
}

export interface TradeDiagnostics {
  net_pnl: number
  gross_pnl: number
  total_commission: number
  commission_pct_of_gross: number | null
  profit_factor: number | null
  expectancy: number | null
  avg_win: number | null
  avg_loss: number | null
  payoff_ratio: number | null
  win_rate_pct: number | null
  median_hold_minutes: number | null
  mean_hold_minutes: number | null
  best_trade_pnl: number | null
  worst_trade_pnl: number | null
  exit_reason_counts: Record<string, number>
  exit_reason_pnl: Record<string, number>
  dominant_exit_reason: string | null
  distributions: TradeDistribution | null
}

export interface FilterDiagnostics {
  rejection_counts: Record<string, number>
  total_rejections: number
  signal_to_trade_pct: number | null
}

export interface CandidateDiagnostics {
  total_candidates: number
  traded_candidates: number
  rejected_candidates: number
}

export interface CandidateRecord {
  candidate_id: string
  strategy_id: string
  symbol: string
  timestamp: string
  side: 'LONG' | 'SHORT'
  entry_price: number
  entry_type: 'CLOSE' | 'NEXT_OPEN' | 'MARKET' | 'LIMIT' | 'MID'
  planned_stop_pct: number
  planned_target_pct: number | null
  planned_horizon_bars: number
  signal_score: number | null
  signal_reason: string | null
  metadata: Record<string, unknown>
  was_traded: boolean
  reject_reason: string | null
}

export interface RiskMetrics {
  sortino_ratio: number | null
  calmar_ratio: number | null
  buy_hold_return_pct: number | null
  alpha_vs_buy_hold_pct: number | null
  exposure_time_pct: number | null
  avg_drawdown_pct: number | null
  max_drawdown_duration: string | null
}

export interface BacktestRunSummary {
  start_value: number
  end_value: number
  return_pct: number
  max_drawdown_pct: number | null
  sharpe_ratio: number | null
  total_trades: number
  won_trades: number
  lost_trades: number
  trade_diagnostics?: TradeDiagnostics | null
  filter_diagnostics?: FilterDiagnostics | null
  risk_metrics?: RiskMetrics | null
}

export interface BacktestRunError {
  type: string
  message: string
}

export interface BacktestOrderRecord {
  datetime: string | null
  status: string
  is_buy: boolean
  size: number
  price: number
  value: number
  commission: number
}

export interface BacktestTradeRecord {
  datetime: string | null
  size: number
  price: number
  value: number
  pnl: number
  pnlcomm: number
  reason?: string | null
  entry_datetime?: string | null
  hold_minutes?: number | null
  hold_bars?: number | null
}

export interface BacktestRejectionRecord {
  datetime: string | null
  symbol: string | null
  reason: string | null
}

export interface BacktestRunResult {
  run_id: string
  name: string | null
  status: 'success' | 'failed'
  strategy: string
  symbol: string | null
  data_source: string
  summary: BacktestRunSummary | null
  analyzers: Record<string, unknown>
  orders: BacktestOrderRecord[]
  trades: BacktestTradeRecord[]
  rejections?: BacktestRejectionRecord[]
  candidates?: CandidateRecord[]
  error: BacktestRunError | null
}

export interface EquityPoint {
  datetime: string
  value: number
}

export interface StrategyAggregate {
  strategy: string
  symbols: string[]
  run_ids: string[]
  successful_runs: number
  failed_runs: number
  summary: BacktestRunSummary
  equity_curve: EquityPoint[]
}

export interface PortfolioAggregate {
  total_net_pnl: number
  total_trades: number
  won_trades: number
  lost_trades: number
  win_rate_pct: number | null
  combined_return_pct: number | null
  best_run_id: string | null
  worst_run_id: string | null
}

export interface ReportAggregates {
  portfolio: PortfolioAggregate | null
  by_strategy: StrategyAggregate[]
}

export interface BacktestReport {
  generated_at: string
  app_version: string
  config_sha256: string
  input_config_path: string | null
  input_config: Record<string, unknown>
  total_runs: number
  successful_runs: number
  failed_runs: number
  status: BacktestReportStatus
  results: BacktestRunResult[]
  aggregates?: ReportAggregates | null
}

export interface BacktestSelectionSummary {
  start_date: string
  end_date: string
  resolution: string
  feed: BacktestFeed
  symbols: string[]
  strategies: string[]
}

export type BacktestExecutionBackend = 'local' | 'argo'
export type ArgoSplitBy = 'run' | 'symbol' | 'strategy' | 'symbol_strategy'

export interface BacktestListItem {
  id: string
  created_at: string
  updated_at: string
  status: BacktestJobStatus
  report_status: BacktestReportStatus | null
  total_runs: number
  completed_runs: number
  successful_runs: number
  failed_runs: number
  selection: BacktestSelectionSummary | null
  error_message: string | null
  execution_backend?: BacktestExecutionBackend
  workflow_name?: string | null
  workflow_namespace?: string | null
}

export interface BacktestCreateResponse {
  backtest_id: string
  status: BacktestJobStatus
  status_url: string
  detail_url: string
}

export interface BacktestArgoLaunchRequest {
  config_path?: string
  config_text?: string
  format?: 'json' | 'yaml'
  split_by?: ArgoSplitBy
  backtest_id?: string
  name?: string
}

export interface BacktestArgoLaunchResponse {
  backtest_id: string
  workflow_name: string
  status: BacktestJobStatus
  status_url: string
  detail_url: string
  workflow_namespace: string
  config_path: string
  output_path: string
}

export interface BacktestDetailResponse {
  metadata: BacktestListItem
  output_path: string | null
  report: BacktestReport | null
}

export interface BacktestStatusResponse extends BacktestListItem {
  progress_pct: number
  is_terminal: boolean
}

export interface BacktestStrategySelectionInput {
  name: string
  params: Record<string, unknown>
}

export interface BacktestCreateRequest {
  start_date: string
  end_date: string
  resolution: string
  feed: BacktestFeed
  symbols: string[]
  strategies: BacktestStrategySelectionInput[]
  broker?: {
    cash: number
    commission: number
    slippage_perc: number
    sizer: 'fixed'
  }
  analyzers?: {
    include_equity_curve: boolean
    include_trade_log: boolean
    include_order_log: boolean
    include_candidate_log: boolean
  }
  execution?: {
    fill_model: 'close' | 'next_bar'
  }
}

export interface BacktestPortfolioSummary {
  total_net_pnl: number
  total_trades: number
  won_trades: number
  lost_trades: number
  win_rate_pct: number | null
}
