import { readApiError } from './errors'
import type {
  DatasetCreateRequest,
  DatasetCreateResponse,
  DatasetDetailResponse,
  DatasetListPageResponse,
  DatasetStatusResponse,
  DatasetWorkflowErrorResponse,
} from '../types/datasets'

export async function createDataset(payload: DatasetCreateRequest): Promise<DatasetCreateResponse> {
  const response = await fetch('/api/datasets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create dataset'))
  }
  return response.json() as Promise<DatasetCreateResponse>
}

export async function fetchDatasets(): Promise<DatasetListPageResponse> {
  const response = await fetch('/api/datasets')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load datasets'))
  }
  return response.json() as Promise<DatasetListPageResponse>
}

export async function fetchDatasetDetail(datasetId: string): Promise<DatasetDetailResponse> {
  const response = await fetch(`/api/datasets/${datasetId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load dataset detail'))
  }
  return response.json() as Promise<DatasetDetailResponse>
}

export async function fetchDatasetStatus(datasetId: string): Promise<DatasetStatusResponse> {
  const response = await fetch(`/api/datasets/${datasetId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load dataset status'))
  }
  return response.json() as Promise<DatasetStatusResponse>
}

export async function retryDataset(datasetId: string): Promise<DatasetCreateResponse> {
  const response = await fetch(`/api/datasets/${datasetId}/retry`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to retry dataset'))
  }
  return response.json() as Promise<DatasetCreateResponse>
}

export async function fetchDatasetWorkflowErrors(datasetId: string): Promise<DatasetWorkflowErrorResponse> {
  const response = await fetch(`/api/datasets/${datasetId}/workflow-errors`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load dataset workflow errors'))
  }
  return response.json() as Promise<DatasetWorkflowErrorResponse>
}

export async function deleteDataset(datasetId: string): Promise<void> {
  const response = await fetch(`/api/datasets/${datasetId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete dataset'))
  }
}

export async function downloadDatasetParquet(datasetId: string): Promise<void> {
  const response = await fetch(`/api/datasets/${datasetId}/download`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to download dataset parquet'))
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i)
  const filename = filenameMatch?.[1] ?? `${datasetId}.parquet`

  const url = window.URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
  } finally {
    window.URL.revokeObjectURL(url)
  }
}
