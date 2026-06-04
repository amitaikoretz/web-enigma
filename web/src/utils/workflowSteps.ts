import type { ArgoWorkflow, ArgoWorkflowNode, ArgoWorkflowParameter } from '../types/argo'

export interface WorkflowStepArgument {
  name: string
  value: string
}

export interface WorkflowStepSummary {
  id: string
  name: string
  displayName: string
  nodeLabel: string
  templateName: string | null
  podName: string
  phase: string | null
  startedAt: string | null
  finishedAt: string | null
  durationLabel: string | null
  inputArguments: WorkflowStepArgument[]
  outputArguments: WorkflowStepArgument[]
  errorOutputs: WorkflowStepArgument[]
  searchText: string
  rawNode: ArgoWorkflowNode
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    return String(value)
  }
}

function normalizeParameter(parameter: ArgoWorkflowParameter): WorkflowStepArgument | null {
  const name = typeof parameter.name === 'string' ? parameter.name.trim() : ''
  if (!name) {
    return null
  }
  const value = stringifyValue(parameter.value)
  return { name, value: value || '—' }
}

function durationLabel(startedAt: string | null | undefined, finishedAt: string | null | undefined): string | null {
  if (!startedAt || !finishedAt) {
    return null
  }
  const started = Date.parse(startedAt)
  const finished = Date.parse(finishedAt)
  if (Number.isNaN(started) || Number.isNaN(finished) || finished < started) {
    return null
  }
  const seconds = Math.max(0, Math.round((finished - started) / 1000))
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  if (minutes < 60) {
    return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)
  const minuteRemainder = minutes % 60
  return minuteRemainder > 0 ? `${hours}h ${minuteRemainder}m` : `${hours}h`
}

function collectArguments(parameters: ArgoWorkflowParameter[] | undefined): WorkflowStepArgument[] {
  if (!Array.isArray(parameters)) {
    return []
  }
  return parameters.map(normalizeParameter).filter((item): item is WorkflowStepArgument => item !== null)
}

function buildSearchText(parts: Array<string | null | undefined>): string {
  return parts
    .filter((part): part is string => typeof part === 'string' && part.trim().length > 0)
    .join(' ')
    .toLowerCase()
}

function stripArgoSuffix(label: string): string {
  const trimmed = label.trim()
  if (!trimmed) {
    return trimmed
  }
  const suffixMatch = trimmed.match(/^(.*)\(\d+:.+\)$/)
  if (suffixMatch?.[1]) {
    return suffixMatch[1].trim() || trimmed
  }
  return trimmed
}

function derivePodName(node: ArgoWorkflowNode): string | null {
  const explicitPodName = typeof node.podName === 'string' && node.podName.trim() ? node.podName.trim() : null
  if (explicitPodName) {
    return explicitPodName
  }

  const nodeName = typeof node.name === 'string' ? node.name.trim() : ''
  if (!nodeName) {
    return null
  }

  const bracketIndex = nodeName.indexOf('[')
  const derivedName = bracketIndex > 0 ? nodeName.slice(0, bracketIndex).trim() : ''
  if (!derivedName) {
    return null
  }

  return derivedName
}

function isRenderableStep(node: ArgoWorkflowNode): boolean {
  return Boolean(node.outputs || node.inputs || node.phase || node.templateName || node.displayName || node.name || node.podName)
}

export function normalizeWorkflowSteps(workflow: ArgoWorkflow): WorkflowStepSummary[] {
  const nodes = workflow.status?.nodes ?? {}
  const entries = Object.values(nodes)
    .map((node) => {
      if (!node || !isRenderableStep(node)) {
        return null
      }
      const inputArguments = collectArguments(node.inputs?.parameters)
      const outputArguments = collectArguments(node.outputs?.parameters)
      const startedAt = node.startedAt ?? null
      const finishedAt = node.finishedAt ?? null
      const templateName = typeof node.templateName === 'string' && node.templateName.trim() ? node.templateName.trim() : null
      const podName = derivePodName(node)
      if (!podName) {
        return null
      }
      const rawLabel = node.displayName?.trim() || node.name?.trim() || templateName || 'Workflow step'
      const nodeLabel = stripArgoSuffix(rawLabel)
      const displayName = nodeLabel
      const nodeName = typeof node.name === 'string' && node.name.trim() ? node.name.trim() : null
      const searchText = buildSearchText([
        nodeName,
        podName,
        displayName,
        nodeLabel,
        rawLabel,
        templateName,
        node.phase ?? null,
        node.message ?? null,
        ...inputArguments.map((arg) => `${arg.name} ${arg.value}`),
        ...outputArguments.map((arg) => `${arg.name} ${arg.value}`),
      ])

      return {
        id: node.id?.trim() || nodeName || podName || displayName,
        name: nodeName || nodeLabel,
        displayName,
        nodeLabel,
        templateName,
        podName,
        phase: node.phase ?? null,
        startedAt,
        finishedAt,
        durationLabel: durationLabel(startedAt, finishedAt),
        inputArguments,
        outputArguments,
        errorOutputs: outputArguments.filter((arg) => arg.name.startsWith('error-')),
        searchText,
        rawNode: node,
      }
    })
    .filter((entry): entry is WorkflowStepSummary => entry !== null)

  return entries.sort((left, right) => {
    const leftTime = left.startedAt ? Date.parse(left.startedAt) : Number.POSITIVE_INFINITY
    const rightTime = right.startedAt ? Date.parse(right.startedAt) : Number.POSITIVE_INFINITY
    if (leftTime !== rightTime) {
      return leftTime - rightTime
    }
    return left.displayName.localeCompare(right.displayName)
  })
}

export function formatWorkflowStepCount(steps: WorkflowStepSummary[]): string {
  return `${steps.length} step${steps.length === 1 ? '' : 's'}`
}
