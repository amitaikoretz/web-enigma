import type { ApiHealthResponse } from '../types/health'

export async function fetchApiHealth(signal?: AbortSignal): Promise<ApiHealthResponse> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`)
  }

  const body = (await response.json()) as ApiHealthResponse
  if (body.status !== 'ok') {
    throw new Error(`Unexpected health status: ${body.status}`)
  }

  return body
}
