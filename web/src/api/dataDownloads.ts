import { readApiError } from './errors'
import type {
  DataDownloadCreateRequest,
  DataDownloadCreateResponse,
  DataDownloadDetailResponse,
  DataDownloadStatusResponse,
} from '../types/dataDownloads'

export async function createDataDownload(
  payload: DataDownloadCreateRequest,
): Promise<DataDownloadCreateResponse> {
  const response = await fetch('/api/market-data/downloads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create data download job'))
  }

  return response.json() as Promise<DataDownloadCreateResponse>
}

export async function fetchDataDownloads(): Promise<DataDownloadStatusResponse[]> {
  const response = await fetch('/api/market-data/downloads')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load data download jobs'))
  }
  return response.json() as Promise<DataDownloadStatusResponse[]>
}

export async function fetchDataDownloadDetail(jobId: string): Promise<DataDownloadDetailResponse> {
  const response = await fetch(`/api/market-data/downloads/${jobId}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load data download detail'))
  }
  return response.json() as Promise<DataDownloadDetailResponse>
}

export async function fetchDataDownloadStatus(jobId: string): Promise<DataDownloadStatusResponse> {
  const response = await fetch(`/api/market-data/downloads/${jobId}/status`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load data download status'))
  }
  return response.json() as Promise<DataDownloadStatusResponse>
}
