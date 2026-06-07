import type { MarketDataResponse } from './marketData'

export type DailyIndexForecastStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'
export type DailyIndexForecastSplitLabel = 'train' | 'validation' | 'test' | 'holdout' | 'other'

export type DailyIndexTaskType = 'regression'

export interface DailyIndexSeriesSpec {
  symbol?: string | null
  data: Record<string, unknown>
}

export interface DailyIndexUniverseConfig {
  start_date: string
  end_date: string
  decision_times: string[]
  symbols: DailyIndexSeriesSpec[]
  benchmark?: DailyIndexSeriesSpec | null
}

export interface DailyIndexFeatureConfig {
  opening_window_minutes: number
  rolling_sessions: number[]
  benchmark_sessions: number[]
  use_calendar_features: boolean
  use_cross_market_features: boolean
}

export interface DailyIndexWalkForwardConfig {
  train_days: number
  validation_days: number
  test_days: number
  step_days: number
  embargo_days: number
  holdout_days: number
  min_train_rows: number
  min_validation_rows: number
  min_test_rows: number
  min_holdout_rows: number
}

export interface DailyIndexTrainConfig {
  alpha_grid: number[]
  residual_distribution: 'normal'
  random_seed: number
}

export interface DailyIndexCostConfig {
  spread_bps: number
  slippage_bps: number
  impact_bps: number
}

export interface DailyIndexForecastCreateRequest {
  name?: string | null
  universe: DailyIndexUniverseConfig
  feature_config: DailyIndexFeatureConfig
  walk_forward: DailyIndexWalkForwardConfig
  train_config: DailyIndexTrainConfig
  costs: DailyIndexCostConfig
  data_cache: Record<string, unknown>
}

export interface DailyIndexForecastCreateResponse {
  group_id: string
  feature_run_id: string
  name?: string | null
  status: DailyIndexForecastStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
}

export interface DailyIndexForecastUpdateRequest {
  name?: string | null
}

export interface DailyIndexForecastDatasetManifestSummary {
  generated_at: string
  dataset_version: string
  feature_version: string
  label_version: string
  model_version: string
  config_hash: string
  symbol_count: number
  benchmark_symbol?: string | null
  start_date: string
  end_date: string
  decision_times: string[]
  total_source_rows: number
  feature_rows: number
  label_rows: number
  joined_rows: number
  dropped_feature_rows: number
  dropped_label_rows: number
  output_path: string
  features_path: string
  labels_path: string
  feature_columns: string[]
}

export interface DailyIndexForecastTargetRow {
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

export interface DailyIndexForecastFeatureRun {
  feature_run_id: string
  status: DailyIndexForecastStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  symbol: string
  benchmark_symbol?: string | null
  decision_times: string[]
  start_date: string
  end_date: string
  params: Record<string, unknown>
  artifact_dir: string
  manifest?: DailyIndexForecastDatasetManifestSummary | null
  summary_metrics?: Record<string, unknown> | null
  features_parquet_path?: string | null
  labels_parquet_path?: string | null
  created_at: string
  updated_at: string
}

export interface DailyIndexForecastListItem {
  group_id: string
  feature_run_id: string
  name?: string | null
  created_at: string
  updated_at: string
  status: DailyIndexForecastStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  symbol: string
  benchmark_symbol?: string | null
  decision_times: string[]
  start_date: string
  end_date: string
  targets: string[]
  targets_total: number
  targets_done: number
  summary_metrics?: Record<string, unknown> | null
  artifact_dir: string
  feature_run_artifact_dir: string
}

export interface DailyIndexForecastDetail {
  group_id: string
  feature_run_id: string
  name?: string | null
  created_at: string
  updated_at: string
  status: DailyIndexForecastStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  params: Record<string, unknown>
  artifact_dir: string
  summary_metrics?: Record<string, unknown> | null
  feature_run?: DailyIndexForecastFeatureRun | null
  dataset_manifest?: DailyIndexForecastDatasetManifestSummary | null
  targets: DailyIndexForecastTargetRow[]
}

export interface DailyIndexForecastStatusResponse {
  group_id: string
  feature_run_id: string
  name?: string | null
  status: DailyIndexForecastStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  argo_phase?: string | null
  progress_pct: number
}

export interface DailyIndexForecastWorkflowErrorResponse {
  group_id: string
  feature_run_id: string
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

export interface DailyIndexForecastChartPredictionRow {
  session_date: string
  decision_time: string
  decision_timestamp: string
  predicted_bps: number
  actual_bps?: number | null
  actual_after_cost?: boolean | null
  split_label: DailyIndexForecastSplitLabel
}

export interface DailyIndexForecastChartResponse {
  group_id: string
  symbol: string
  selected_date: string
  resolution: string
  cache_status: string
  source: 'stored' | 'computed'
  bars: MarketDataResponse
  split_label: DailyIndexForecastSplitLabel
  predictions: DailyIndexForecastChartPredictionRow[]
}
