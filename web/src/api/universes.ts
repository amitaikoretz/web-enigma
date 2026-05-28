import type { SymbolUniverse, SymbolUniverseConstituents } from '../types/universes'
import { readApiError } from './errors'

export async function fetchUniverses(activeOnly = true): Promise<SymbolUniverse[]> {
  const query = new URLSearchParams()
  query.set('active_only', String(activeOnly))
  const response = await fetch(`/api/universes?${query.toString()}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load universes'))
  }
  return response.json() as Promise<SymbolUniverse[]>
}

export async function fetchUniverseConstituents(key: string, asOf: string): Promise<SymbolUniverseConstituents> {
  const query = new URLSearchParams()
  query.set('as_of', asOf)
  const response = await fetch(`/api/universes/${encodeURIComponent(key)}/constituents?${query.toString()}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load universe constituents'))
  }
  return response.json() as Promise<SymbolUniverseConstituents>
}

export async function createUniverse(payload: {
  key: string
  name: string
  description?: string | null
  provider: string
  provider_ref: Record<string, unknown>
  is_active: boolean
}): Promise<SymbolUniverse> {
  const response = await fetch('/api/universes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create universe'))
  }
  return response.json() as Promise<SymbolUniverse>
}

export async function patchUniverse(
  key: string,
  payload: Partial<{
    name: string
    description: string | null
    provider: string
    provider_ref: Record<string, unknown>
    is_active: boolean
  }>,
): Promise<SymbolUniverse> {
  const response = await fetch(`/api/universes/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update universe'))
  }
  return response.json() as Promise<SymbolUniverse>
}

export async function refreshUniverse(
  key: string,
  asOf: string,
): Promise<{ workflow_name: string; namespace: string }> {
  const response = await fetch(`/api/universes/${encodeURIComponent(key)}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ as_of: asOf }),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to submit universe refresh'))
  }
  return response.json() as Promise<{ workflow_name: string; namespace: string }>
}

export async function refreshAllUniverses(
  asOf: string,
): Promise<{ workflow_name: string; namespace: string }> {
  const response = await fetch('/api/universes/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ as_of: asOf }),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to submit universe refresh'))
  }
  return response.json() as Promise<{ workflow_name: string; namespace: string }>
}

export async function syncUniverseRegistry(): Promise<{ workflow_name: string; namespace: string }> {
  const response = await fetch('/api/universes/sync-registry', {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to submit universe registry sync'))
  }
  return response.json() as Promise<{ workflow_name: string; namespace: string }>
}

export async function createUserUniverse(payload: {
  name: string
  description?: string | null
  symbols: string[]
  is_active?: boolean
}): Promise<SymbolUniverse> {
  const response = await fetch('/api/universes/user', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to create user universe'))
  }
  return response.json() as Promise<SymbolUniverse>
}

export async function patchUserUniverse(
  key: string,
  payload: Partial<{ name: string; description: string | null; is_active: boolean }>,
): Promise<SymbolUniverse> {
  const response = await fetch(`/api/universes/user/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update user universe'))
  }
  return response.json() as Promise<SymbolUniverse>
}

export async function replaceUserUniverseSymbols(
  key: string,
  payload: { symbols: string[]; effective_on?: string },
): Promise<{ key: string; effective_on: string; added: number; closed: number; unchanged: number }> {
  const response = await fetch(`/api/universes/user/${encodeURIComponent(key)}/symbols`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to update user universe symbols'))
  }
  return response.json() as Promise<{ key: string; effective_on: string; added: number; closed: number; unchanged: number }>
}

export async function deleteUserUniverse(key: string): Promise<void> {
  const response = await fetch(`/api/universes/user/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to delete user universe'))
  }
}
