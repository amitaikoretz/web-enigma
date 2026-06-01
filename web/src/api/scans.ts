import type { ScanCreateRequest, ScanListResponse, ScanStatusResponse, ScanType } from '../types/scans'

export async function createScanRun(scanType: ScanType, request: ScanCreateRequest): Promise<ScanStatusResponse> {
  const response = await fetch(`/api/scanners/${scanType}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Failed to create scan: ${response.status} ${text}`)
  }
  return response.json() as Promise<ScanStatusResponse>
}

export async function fetchScanRuns(scanType: ScanType): Promise<ScanListResponse> {
  const response = await fetch(`/api/scanners/${scanType}/runs`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Failed to load scans: ${response.status} ${text}`)
  }
  return response.json() as Promise<ScanListResponse>
}

export async function fetchScanRun(scanType: ScanType, scanId: string): Promise<ScanStatusResponse> {
  const response = await fetch(`/api/scanners/${scanType}/runs/${scanId}`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Failed to load scan: ${response.status} ${text}`)
  }
  return response.json() as Promise<ScanStatusResponse>
}

export async function fetchScanResults(scanType: ScanType, scanId: string): Promise<unknown> {
  const response = await fetch(`/api/scanners/${scanType}/runs/${scanId}/results`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Failed to load results: ${response.status} ${text}`)
  }
  return response.json() as Promise<unknown>
}

export async function fetchScanParams(
  scanType: ScanType,
): Promise<{ defaults: Record<string, unknown>; schema: unknown }> {
  const response = await fetch(`/api/scanners/${scanType}/params`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Failed to load params schema: ${response.status} ${text}`)
  }
  return response.json() as Promise<{ defaults: Record<string, unknown>; schema: unknown }>
}
