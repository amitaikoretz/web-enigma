export type RiskModelStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'

export type RiskModelTaskType = 'classification' | 'regression'

export interface RiskModelTargetSpec {
  target_key: string
  task_type: RiskModelTaskType
}

export interface RiskModelCreateRequest {
  backtest_ids: string[]
  targets: RiskModelTargetSpec[]
  dataset_config: Record<string, unknown>
  train_config: Record<string, unknown>
}

export interface RiskModelCreateResponse {
  group_id: string
  status: RiskModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
}

export interface RiskModelListItem {
  group_id: string
  created_at: string
  updated_at: string
  status: RiskModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  backtest_ids: string[]
  targets: string[]
  summary_metrics?: Record<string, unknown> | null
  artifact_dir: string
}

export interface RiskModelTargetRow {
  id: number
  group_id: string
  target_key: string
  task_type: string
  status: string
  model_artifact_path?: string | null
  metrics?: Record<string, unknown> | null
  dataset_manifest_path?: string | null
  feature_columns?: string[] | null
  created_at: string
  updated_at: string
}

export interface RiskModelDetail {
  group_id: string
  created_at: string
  updated_at: string
  status: RiskModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  params: Record<string, unknown>
  artifact_dir: string
  summary_metrics?: Record<string, unknown> | null
  sources: Array<Record<string, unknown>>
  targets: RiskModelTargetRow[]
}

