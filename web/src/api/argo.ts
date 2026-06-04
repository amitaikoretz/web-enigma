import { readApiError } from './errors'
import type {
  ArgoWorkflow,
  ArgoWorkflowDebugConfigResponse,
  ArgoWorkflowPodLogsResponse,
} from '../types/argo'

export async function fetchWorkflow(
  workflowName: string,
  namespace?: string | null,
): Promise<ArgoWorkflow> {
  const searchParams = new URLSearchParams()
  if (namespace) {
    searchParams.set('namespace', namespace)
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : ''
  const response = await fetch(`/api/argo/workflows/${encodeURIComponent(workflowName)}${suffix}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load workflow'))
  }
  return response.json() as Promise<ArgoWorkflow>
}

export async function fetchWorkflowDebugConfig(
  workflowName: string,
  podName: string,
  namespace?: string | null,
): Promise<ArgoWorkflowDebugConfigResponse> {
  const searchParams = new URLSearchParams()
  if (namespace) {
    searchParams.set('namespace', namespace)
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : ''
  const response = await fetch(
    `/api/argo/workflows/${encodeURIComponent(workflowName)}/pods/${encodeURIComponent(podName)}/debug-config${suffix}`,
  )
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load workflow debug configuration'))
  }
  return response.json() as Promise<ArgoWorkflowDebugConfigResponse>
}

export async function fetchWorkflowPodLogs(
  workflowName: string,
  podName: string,
  namespace?: string | null,
): Promise<ArgoWorkflowPodLogsResponse> {
  const searchParams = new URLSearchParams()
  if (namespace) {
    searchParams.set('namespace', namespace)
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : ''
  const response = await fetch(
    `/api/argo/workflows/${encodeURIComponent(workflowName)}/pods/${encodeURIComponent(podName)}/logs${suffix}`,
  )
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load workflow pod logs'))
  }
  return response.json() as Promise<ArgoWorkflowPodLogsResponse>
}
