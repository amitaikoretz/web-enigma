export type Resolution = '1m' | '5m' | '15m' | '1h' | '1d'

export interface MarketDataRow {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface MarketDataResponse {
  symbol: string
  provider: 'alpaca'
  resolution: string
  start_date: string
  stop_date: string
  cache_status: string
  rows: MarketDataRow[]
}

export interface ChartQuery {
  symbol: string
  startDate: string
  numDays: number
  resolution: Resolution
}
