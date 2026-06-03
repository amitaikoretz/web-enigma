import { readApiError } from './errors'
import type {
  RiskModelCreateRequest,
  RiskModelCreateResponse,
  RiskModelDetail,
  RiskModelListItem,
  RiskModelStatusResponse,
  RiskModelWorkflowErrorResponse,
} from '../types/riskModels'

export async function createRiskModel(
  payload: RiskModelCreateRequest,
): Promise<RiskModelCreateResponse> {
  const response = await fetch('/api/risk-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create risk model'))
  }

  return response.json() as Promise<RiskModelCreateResponse>
}

export async function retryRiskModel(groupId: string): Promise<RiskModelCreateResponse> {
  const response = await fetch(`/api/risk-models/${groupId}/retry`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to retry risk model'))
  }

  return response.json() as Promise<RiskModelCreateResponse>
}

export async function fetchRiskModels(): Promise<RiskModelListItem[]> {
  const response = await fetch('/api/risk-models')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk models'))
  }
  return response.json() as Promise<RiskModelListItem[]>
}

export async function fetchRiskModelStatus(groupId: string): Promise<RiskModelStatusResponse> {
  const response = await fetch(`/api/risk-models/${groupId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk model status'))
  }
  return response.json() as Promise<RiskModelStatusResponse>
}

export async function fetchRiskModelDetail(groupId: string): Promise<RiskModelDetail> {
  const response = await fetch(`/api/risk-models/${groupId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk model'))
  }
  return response.json() as Promise<RiskModelDetail>
}

export async function fetchRiskModelWorkflowErrors(
  groupId: string,
): Promise<RiskModelWorkflowErrorResponse> {
  const response = await fetch(`/api/risk-models/${groupId}/workflow-errors`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk model workflow errors'))
  }
  return response.json() as Promise<RiskModelWorkflowErrorResponse>
}

export async function deleteRiskModel(groupId: string): Promise<void> {
  const response = await fetch(`/api/risk-models/${groupId}`, { method: 'DELETE' })
  if (response.status === 204) {
    return
  }
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete risk model'))
  }
}
