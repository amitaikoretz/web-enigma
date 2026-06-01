export type ScanType = 'momentum' | 'options' | 'trend'
export type ScanStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface ScanStatusResponse {
  scan_id: string
  scan_type: ScanType
  status: ScanStatus
  created_at: string
  updated_at: string
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  params: Record<string, unknown>
  results_json_path?: string | null
  error_exception?: string | null
  error_code_location?: string | null
  error_call_stack?: string | null
  error_traceback?: string | null
}

export interface ScanCreateRequest {
  params: Record<string, unknown>
}

export interface ScanListResponse {
  items: ScanStatusResponse[]
}

