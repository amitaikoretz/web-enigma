export interface ServerInfo {
  backtest_results_dir: string
  backtest_cache_dir: string
  platform_settings_path: string
  argo_workflows_enabled?: boolean
  backtest_execution_backend?: string
}
