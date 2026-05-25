import { readApiError } from './errors'
import type {
  BacktestCreateRequest,
  BacktestCreateResponse,
  BacktestDetailResponse,
  BacktestListItem,
  BacktestStatusResponse,
} from '../types/backtests'

export async function createBacktest(
  payload: BacktestCreateRequest,
): Promise<BacktestCreateResponse> {
  const response = await fetch('/api/backtests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create backtest'))
  }

  return response.json() as Promise<BacktestCreateResponse>
}

export async function fetchBacktests(): Promise<BacktestListItem[]> {
  const response = await fetch('/api/backtests')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load backtests'))
  }
  return response.json() as Promise<BacktestListItem[]>
}

export async function fetchBacktestDetail(backtestId: string): Promise<BacktestDetailResponse> {
  const response = await fetch(`/api/backtests/${backtestId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load backtest detail'))
  }
  return response.json() as Promise<BacktestDetailResponse>
}

export async function fetchBacktestStatus(backtestId: string): Promise<BacktestStatusResponse> {
  const response = await fetch(`/api/backtests/${backtestId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load backtest status'))
  }
  return response.json() as Promise<BacktestStatusResponse>
}

export function backtestReportUrl(backtestId: string): string {
  return `/api/backtests/${backtestId}/report`
}

export function backtestConfigUrl(backtestId: string): string {
  return `/api/backtests/${backtestId}/config`
}

export async function deleteBacktest(backtestId: string): Promise<void> {
  const response = await fetch(`/api/backtests/${backtestId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete backtest'))
  }
}
