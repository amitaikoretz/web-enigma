import { readApiError } from './errors'
import type { ServerInfo } from '../types/serverInfo'

export async function fetchServerInfo(): Promise<ServerInfo> {
  const response = await fetch('/api/server/info')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load server info'))
  }
  return response.json() as Promise<ServerInfo>
}
