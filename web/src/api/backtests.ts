import { readApiError } from './errors'
import { parse as parseYaml } from 'yaml'
import type {
  BacktestArgoLaunchRequest,
  BacktestArgoLaunchResponse,
  BacktestCreateRequest,
  BacktestCreateResponse,
  BacktestDetailResponse,
  BacktestListPageResponse,
  BacktestListItem,
  BacktestStatusResponse,
  BacktestUpdateRequest,
} from '../types/backtests'

export interface FetchBacktestsParams {
  page?: number
  pageSize?: number
}

function normalizeBacktestListPage(
  body: unknown,
  params: FetchBacktestsParams,
): BacktestListPageResponse {
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 25

  if (Array.isArray(body)) {
    const offset = (page - 1) * pageSize
    const items = body as BacktestListPageResponse['items']
    return {
      items: items.slice(offset, offset + pageSize),
      total: items.length,
      page,
      page_size: pageSize,
    }
  }

  const record = body as Partial<BacktestListPageResponse>
  const items = Array.isArray(record.items) ? record.items : []
  return {
    items,
    total: typeof record.total === 'number' ? record.total : items.length,
    page: typeof record.page === 'number' ? record.page : page,
    page_size: typeof record.page_size === 'number' ? record.page_size : pageSize,
  }
}

export async function retryBacktest(backtestId: string): Promise<BacktestCreateResponse> {
  const response = await fetch(`/api/backtests/${backtestId}/retry`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to retry backtest'))
  }

  return response.json() as Promise<BacktestCreateResponse>
}

export async function fetchBacktestConfigYaml(backtestId: string): Promise<string> {
  const response = await fetch(backtestConfigUrl(backtestId))
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load backtest configuration'))
  }
  return response.text()
}

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

export async function launchArgoBacktest(
  payload: BacktestArgoLaunchRequest,
): Promise<BacktestArgoLaunchResponse> {
  const response = await fetch('/api/backtests/argo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to launch Argo backtest'))
  }

  return response.json() as Promise<BacktestArgoLaunchResponse>
}

export async function fetchBacktests(
  params: FetchBacktestsParams = {},
): Promise<BacktestListPageResponse> {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params.page ?? 1))
  searchParams.set('page_size', String(params.pageSize ?? 25))
  const response = await fetch(`/api/backtests?${searchParams.toString()}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load backtests'))
  }
  const body: unknown = await response.json()
  return normalizeBacktestListPage(body, params)
}

export async function fetchBacktestInputConfig(backtestId: string): Promise<Record<string, unknown>> {
  const detail = await fetchBacktestDetail(backtestId)
  if (detail.report?.input_config) {
    return detail.report.input_config
  }

  const yamlText = await fetchBacktestConfigYaml(backtestId)
  const parsed = parseYaml(yamlText)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('Backtest configuration is not available yet.')
  }
  return parsed as Record<string, unknown>
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

export async function updateBacktest(
  backtestId: string,
  payload: BacktestUpdateRequest,
): Promise<BacktestListItem> {
  const response = await fetch(`/api/backtests/${backtestId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update backtest'))
  }

  return response.json() as Promise<BacktestListItem>
}
