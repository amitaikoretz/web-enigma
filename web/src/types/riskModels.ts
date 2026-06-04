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

export interface RiskModelStatusResponse {
  group_id: string
  status: RiskModelStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  argo_phase?: string | null
}

export interface RiskModelWorkflowErrorResponse {
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

export interface RiskDatasetManifestSummary {
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

export interface RiskModelListItem {
  group_id: string
  created_at: string
  updated_at: string
  status: RiskModelStatus
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

export interface RiskModelSourceRow {
  backtest_id: string
  source_report_path?: string | null
  created_at?: string | null
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
  dataset_manifest?: RiskDatasetManifestSummary | null
  sources: RiskModelSourceRow[]
  targets: RiskModelTargetRow[]
  training_start_date?: string | null
  training_end_date?: string | null
}
