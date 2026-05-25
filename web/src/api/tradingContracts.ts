import { readApiError } from './errors'
import type { TradingContract, TradingContractCreatePayload, TradingContractUpdatePayload } from '../types/tradingContracts'

export interface TradingContractListFilters {
  symbol?: string
  strategy?: string
}

export interface TradingContractActiveFilters extends TradingContractListFilters {
  active_at?: string
}

export async function fetchTradingContracts(
  filters: TradingContractListFilters = {},
): Promise<TradingContract[]> {
  const params = new URLSearchParams()
  if (filters.symbol) {
    params.set('symbol', filters.symbol)
  }
  if (filters.strategy) {
    params.set('strategy', filters.strategy)
  }
  const query = params.toString()
  const response = await fetch(`/api/trading-contracts${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load trading contracts'))
  }
  return response.json() as Promise<TradingContract[]>
}

export async function fetchActiveTradingContracts(
  filters: TradingContractActiveFilters = {},
): Promise<TradingContract[]> {
  const params = new URLSearchParams()
  if (filters.symbol) {
    params.set('symbol', filters.symbol)
  }
  if (filters.strategy) {
    params.set('strategy', filters.strategy)
  }
  if (filters.active_at) {
    params.set('active_at', filters.active_at)
  }
  const query = params.toString()
  const response = await fetch(`/api/trading-contracts/active${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load active trading contracts'))
  }
  return response.json() as Promise<TradingContract[]>
}

export async function createTradingContract(
  payload: TradingContractCreatePayload,
): Promise<TradingContract> {
  const response = await fetch('/api/trading-contracts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create trading contract'))
  }
  return response.json() as Promise<TradingContract>
}

export async function updateTradingContract(
  contractId: string,
  payload: TradingContractUpdatePayload,
): Promise<TradingContract> {
  const response = await fetch(`/api/trading-contracts/${contractId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update trading contract'))
  }
  return response.json() as Promise<TradingContract>
}

export async function deleteTradingContract(contractId: string): Promise<TradingContract> {
  const response = await fetch(`/api/trading-contracts/${contractId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete trading contract'))
  }
  return response.json() as Promise<TradingContract>
}
