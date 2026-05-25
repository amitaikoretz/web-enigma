import { readApiError } from './errors'
import type { ServerPlatformSettings } from '../types/settings'

export async function fetchPlatformSettings(): Promise<ServerPlatformSettings> {
  const response = await fetch('/api/settings')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load platform settings'))
  }
  return response.json() as Promise<ServerPlatformSettings>
}

export async function updatePlatformSettings(
  payload: ServerPlatformSettings,
): Promise<ServerPlatformSettings> {
  const response = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to save platform settings'))
  }
  return response.json() as Promise<ServerPlatformSettings>
}
