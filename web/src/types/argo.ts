export interface ArgoWorkflowParameter {
  name?: string | null
  value?: unknown
}

export interface ArgoWorkflowNodeArguments {
  parameters?: ArgoWorkflowParameter[]
}

export interface ArgoWorkflowNodeOutputArguments {
  parameters?: ArgoWorkflowParameter[]
}

export interface ArgoWorkflowNode {
  id?: string | null
  name?: string | null
  displayName?: string | null
  phase?: string | null
  templateName?: string | null
  podName?: string | null
  startedAt?: string | null
  finishedAt?: string | null
  message?: string | null
  inputs?: ArgoWorkflowNodeArguments | null
  outputs?: ArgoWorkflowNodeOutputArguments | null
}

export interface ArgoWorkflow {
  metadata?: {
    name?: string | null
    namespace?: string | null
  }
  spec?: {
    templates?: Array<Record<string, unknown>>
  }
  status?: {
    phase?: string | null
    message?: string | null
    nodes?: Record<string, ArgoWorkflowNode | null | undefined>
  }
}

export interface ArgoWorkflowDebugConfigResponse {
  workflow_name: string
  namespace: string
  pod_name: string
  terminal_command: string
  launch_configuration: Record<string, unknown>
  snippet: string
}

export interface ArgoWorkflowPodLogsResponse {
  workflow_name: string
  namespace: string
  pod_name: string
  container_name: string | null
  logs: string
}

export interface WorkflowStepsDescriptor {
  entityKind: string
  entityLabel: string
  workflowName: string
  namespace?: string | null
  workflowTitle?: string | null
}
