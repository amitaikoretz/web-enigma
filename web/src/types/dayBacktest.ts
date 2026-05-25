import type { Resolution } from './marketData'
import type { MarketDataRow } from './marketData'

export interface OrderRecord {
  datetime: string | null
  status: string
  is_buy: boolean
  size: number
  price: number
  value: number
  commission: number
}

export interface TradeRecord {
  datetime: string | null
  size: number
  price: number
  value: number
  pnl: number
  pnlcomm: number
}

export interface RunSummary {
  start_value: number
  end_value: number
  return_pct: number
  max_drawdown_pct: number | null
  sharpe_ratio: number | null
  total_trades: number
  won_trades: number
  lost_trades: number
}

export interface RunError {
  type: string
  message: string
}

export interface SingleDayBacktestResult {
  status: 'success' | 'failed'
  summary: RunSummary | null
  orders: OrderRecord[]
  trades: TradeRecord[]
  error: RunError | null
}

export interface SingleDayBacktestResponse {
  symbol: string
  date: string
  resolution: string
  cache_status: string
  bars: MarketDataRow[]
  backtest: SingleDayBacktestResult
}

export interface SingleDayBacktestQuery {
  symbol: string
  date: string
  resolution: Resolution
  strategy: string
  strategyParams: Record<string, unknown>
}
