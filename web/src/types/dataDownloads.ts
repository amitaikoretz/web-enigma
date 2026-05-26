export type DataDownloadJobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DataDownloadFeed = 'iex' | 'sip' | 'otc'

export interface DataDownloadRecordInput {
  symbol: string
  start_date: string
  stop_date: string
  resolution: string
  feed: DataDownloadFeed
  force_refresh?: boolean
}

export interface DataDownloadCreateRequest {
  output_folder: string
  records: DataDownloadRecordInput[]
}

export interface DataDownloadCreateResponse {
  job_id: string
  status: 'pending'
  status_url: string
  detail_url: string
}

export interface DataDownloadStatusResponse {
  job_id: string
  status: DataDownloadJobStatus
  output_folder: string
  total_records: number
  completed_records: number
  successful_records: number
  failed_records: number
  created_at: string
  updated_at: string
  error_message: string | null
}

export interface DataDownloadRecordResult {
  symbol: string
  start_date: string
  stop_date: string
  resolution: string
  feed: string
  cache_status: string | null
  parquet_path: string | null
  row_count: number | null
  error: string | null
}

export interface DataDownloadDetailResponse {
  metadata: DataDownloadStatusResponse
  records: DataDownloadRecordResult[]
}
