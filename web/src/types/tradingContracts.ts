export interface TradingContract {
  id: string
  symbol: string
  strategy: string
  strategy_params: Record<string, unknown>
  start_datetime: string
  end_datetime: string
  maximum_trade_size: number
  total_invested: number
  revision: number
  deleted_at: string | null
  created_at: string
}

export interface TradingContractCreatePayload {
  symbol: string
  strategy: string
  strategy_params: Record<string, unknown>
  start_datetime: string
  end_datetime: string
  maximum_trade_size: number
  total_invested: number
}

export type TradingContractUpdatePayload = Partial<TradingContractCreatePayload>

export type ContractLifecycleStatus = 'upcoming' | 'active' | 'expired'
