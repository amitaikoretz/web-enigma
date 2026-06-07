import { readApiError } from './errors'
import type {
  DailyIndexForecastCreateRequest,
  DailyIndexForecastCreateResponse,
  DailyIndexForecastChartResponse,
  DailyIndexForecastDetail,
  DailyIndexForecastListItem,
  DailyIndexForecastStatusResponse,
  DailyIndexForecastUpdateRequest,
  DailyIndexForecastWorkflowErrorResponse,
} from '../types/dailyIndexForecastModels'

export async function createDailyIndexForecastModel(
  payload: DailyIndexForecastCreateRequest,
): Promise<DailyIndexForecastCreateResponse> {
  const response = await fetch('/api/daily-index-forecast-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create Daily Index Forecast'))
  }

  return response.json() as Promise<DailyIndexForecastCreateResponse>
}

export async function retryDailyIndexForecastModel(
  groupId: string,
): Promise<DailyIndexForecastCreateResponse> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}/retry`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to retry Daily Index Forecast'))
  }

  return response.json() as Promise<DailyIndexForecastCreateResponse>
}

export async function fetchDailyIndexForecastModels(): Promise<DailyIndexForecastListItem[]> {
  const response = await fetch('/api/daily-index-forecast-models')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load Daily Index Forecast models'))
  }
  return response.json() as Promise<DailyIndexForecastListItem[]>
}

export async function fetchDailyIndexForecastModelStatus(
  groupId: string,
): Promise<DailyIndexForecastStatusResponse> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load Daily Index Forecast status'))
  }
  return response.json() as Promise<DailyIndexForecastStatusResponse>
}

export async function fetchDailyIndexForecastModelDetail(
  groupId: string,
): Promise<DailyIndexForecastDetail> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load Daily Index Forecast'))
  }
  return response.json() as Promise<DailyIndexForecastDetail>
}

export async function updateDailyIndexForecastModel(
  groupId: string,
  payload: DailyIndexForecastUpdateRequest,
): Promise<DailyIndexForecastDetail> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update Daily Index Forecast'))
  }

  return response.json() as Promise<DailyIndexForecastDetail>
}

export async function fetchDailyIndexForecastModelWorkflowErrors(
  groupId: string,
): Promise<DailyIndexForecastWorkflowErrorResponse> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}/workflow-errors`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load Daily Index Forecast workflow errors'))
  }
  return response.json() as Promise<DailyIndexForecastWorkflowErrorResponse>
}

export async function fetchDailyIndexForecastModelChartData(
  groupId: string,
  selectedDate: string,
  resolution = '5m',
): Promise<DailyIndexForecastChartResponse> {
  const params = new URLSearchParams({
    selected_date: selectedDate,
    resolution,
  })
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}/chart-data?${params.toString()}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load Daily Index Forecast chart data'))
  }
  return response.json() as Promise<DailyIndexForecastChartResponse>
}

export async function deleteDailyIndexForecastModel(groupId: string): Promise<void> {
  const response = await fetch(`/api/daily-index-forecast-models/${groupId}`, { method: 'DELETE' })
  if (response.status === 204) {
    return
  }
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete Daily Index Forecast'))
  }
}
