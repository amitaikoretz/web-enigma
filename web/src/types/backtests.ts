export type BacktestJobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type BacktestReportStatus = 'success' | 'partial_failure' | 'failure'
export type BacktestFeed = 'iex' | 'sip' | 'otc'

export interface BacktestRunSummary {
  start_value: number
  end_value: number
  return_pct: number
  max_drawdown_pct: number | null
  sharpe_ratio: number | null
  total_trades: number
  won_trades: number
  lost_trades: number
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
  error: BacktestRunError | null
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
}

export interface BacktestSelectionSummary {
  start_date: string
  end_date: string
  resolution: string
  feed: BacktestFeed
  symbols: string[]
  strategies: string[]
}

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
  selection: BacktestSelectionSummary
  error_message: string | null
}

export interface BacktestCreateResponse {
  backtest_id: string
  status: BacktestJobStatus
  status_url: string
  detail_url: string
}

export interface BacktestDetailResponse {
  metadata: BacktestListItem
  output_path: string | null
  report: BacktestReport | null
}

export type BacktestStatusResponse = BacktestListItem

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
  }
  execution?: {
    fill_model: 'close' | 'next_bar'
  }
}
