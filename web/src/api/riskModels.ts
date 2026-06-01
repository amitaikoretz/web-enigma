import { readApiError } from './errors'
import type {
  RiskModelCreateRequest,
  RiskModelCreateResponse,
  RiskModelDetail,
  RiskModelListItem,
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

export async function fetchRiskModels(): Promise<RiskModelListItem[]> {
  const response = await fetch('/api/risk-models')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk models'))
  }
  return response.json() as Promise<RiskModelListItem[]>
}

export async function fetchRiskModelDetail(groupId: string): Promise<RiskModelDetail> {
  const response = await fetch(`/api/risk-models/${groupId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load risk model'))
  }
  return response.json() as Promise<RiskModelDetail>
}

