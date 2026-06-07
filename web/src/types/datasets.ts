export type DatasetJobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DatasetProvider = 'alpaca' | 'yahoo'
export type DatasetResolution = '1m' | '5m' | '15m' | '1h' | '1d'
export type DatasetOptionsFeed = 'indicative' | 'opra'

export interface DatasetOptionsRequest {
  enabled: boolean
  feed: DatasetOptionsFeed
}

export interface DatasetCreateRequest {
  symbol: string
  provider: DatasetProvider
  resolution: DatasetResolution
  start_date: string
  end_date: string
  name?: string | null
  options?: DatasetOptionsRequest
}

export interface DatasetCreateResponse {
  dataset_id: string
  status: 'pending'
  status_url: string
  detail_url: string
}

export interface DatasetListItem {
  id: string
  name: string | null
  symbol: string
  provider: DatasetProvider
  resolution: DatasetResolution
  start_date: string
  end_date: string
  created_at: string
  updated_at: string
  status: DatasetJobStatus
  argo_namespace: string | null
  argo_workflow_name: string | null
  params_json: Record<string, unknown>
  output_dir: string
  dataset_parquet_path: string | null
  manifest_path: string | null
  options_parquet_path: string | null
  options_manifest_path: string | null
  error_message: string | null
  progress_pct?: number
}

export interface DatasetStatusResponse extends DatasetListItem {
  is_terminal: boolean
}

export interface DatasetListPageResponse {
  items: DatasetListItem[]
  total: number
  page: number
  page_size: number
}

export interface DatasetDetailResponse {
  metadata: DatasetListItem
}

export interface DatasetWorkflowErrorResponse {
  dataset_id: string
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
