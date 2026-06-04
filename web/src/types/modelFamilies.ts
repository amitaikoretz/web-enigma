export type ModelStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'

export type ModelTaskType = 'classification' | 'regression'

export interface ModelTargetSpec {
  target_key: string
  task_type: ModelTaskType
}

export interface ModelCreateRequest {
  backtest_ids: string[]
  targets: ModelTargetSpec[]
  dataset_config: Record<string, unknown>
  train_config: Record<string, unknown>
}

export interface ModelCreateResponse {
  group_id: string
  status: ModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
}

export interface ModelStatusResponse {
  group_id: string
  status: ModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  argo_phase?: string | null
}

export interface ModelWorkflowErrorResponse {
  group_id: string
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  argo_phase?: string | null
  available: boolean
  status_message?: string | null
  failed_node_name?: string | null
  failed_template_name?: string | null
  error_exception?: string | null
  error_code_location?: string | null
  error_call_stack: string[]
  error_traceback?: string | null
}

export interface DatasetManifestSummary {
  generated_at: string
  dataset_version: string
  label_version: string
  feature_version: string
  config_hash: string
  source_report_paths: string[]
  total_candidates: number
  labeled_rows: number
  feature_rows: number
  joined_rows: number
  dropped_label_rows: number
  dropped_feature_rows: number
  duplicate_candidate_ids: number
  output_path: string
}

export interface ModelListItem {
  group_id: string
  created_at: string
  updated_at: string
  status: ModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  backtest_ids: string[]
  targets: string[]
  targets_total: number
  targets_done: number
  summary_metrics?: Record<string, unknown> | null
  artifact_dir: string
  training_start_date?: string | null
  training_end_date?: string | null
}

export interface ModelTargetRow {
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

export interface ModelSourceRow {
  backtest_id: string
  source_report_path?: string | null
  created_at?: string | null
}

export interface ModelDetail {
  group_id: string
  created_at: string
  updated_at: string
  status: ModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  params: Record<string, unknown>
  artifact_dir: string
  summary_metrics?: Record<string, unknown> | null
  dataset_manifest?: DatasetManifestSummary | null
  sources: ModelSourceRow[]
  targets: ModelTargetRow[]
  training_start_date?: string | null
  training_end_date?: string | null
}
