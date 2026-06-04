import { readApiError } from './errors'
import type {
  ReturnForecastModelCreateRequest,
  ReturnForecastModelCreateResponse,
  ReturnForecastModelDetail,
  ReturnForecastModelListItem,
  ReturnForecastModelStatusResponse,
  ReturnForecastModelWorkflowErrorResponse,
} from '../types/returnForecastModels'

export async function createReturnForecastModel(
  payload: ReturnForecastModelCreateRequest,
): Promise<ReturnForecastModelCreateResponse> {
  const response = await fetch('/api/return-forecast-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create return forecast model'))
  }

  return response.json() as Promise<ReturnForecastModelCreateResponse>
}

export async function retryReturnForecastModel(
  groupId: string,
): Promise<ReturnForecastModelCreateResponse> {
  const response = await fetch(`/api/return-forecast-models/${groupId}/retry`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to retry return forecast model'))
  }

  return response.json() as Promise<ReturnForecastModelCreateResponse>
}

export async function fetchReturnForecastModels(): Promise<ReturnForecastModelListItem[]> {
  const response = await fetch('/api/return-forecast-models')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load return forecast models'))
  }
  return response.json() as Promise<ReturnForecastModelListItem[]>
}

export async function fetchReturnForecastModelStatus(
  groupId: string,
): Promise<ReturnForecastModelStatusResponse> {
  const response = await fetch(`/api/return-forecast-models/${groupId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load return forecast model status'))
  }
  return response.json() as Promise<ReturnForecastModelStatusResponse>
}

export async function fetchReturnForecastModelDetail(groupId: string): Promise<ReturnForecastModelDetail> {
  const response = await fetch(`/api/return-forecast-models/${groupId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load return forecast model'))
  }
  return response.json() as Promise<ReturnForecastModelDetail>
}

export async function fetchReturnForecastModelWorkflowErrors(
  groupId: string,
): Promise<ReturnForecastModelWorkflowErrorResponse> {
  const response = await fetch(`/api/return-forecast-models/${groupId}/workflow-errors`)
  if (!response.ok) {
    throw new Error(
      await readApiError(response, 'Failed to load return forecast model workflow errors'),
    )
  }
  return response.json() as Promise<ReturnForecastModelWorkflowErrorResponse>
}

export async function deleteReturnForecastModel(groupId: string): Promise<void> {
  const response = await fetch(`/api/return-forecast-models/${groupId}`, { method: 'DELETE' })
  if (response.status === 204) {
    return
  }
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete return forecast model'))
  }
}
