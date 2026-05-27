const ARTIFACT_DESCRIPTIONS: Record<string, string> = {
  config: 'Input YAML written when this backtest was submitted',
  report_json: 'Slim JSON index; detailed run data lives in sidecar files',
  report_parquet: 'Per-run headline metrics: return, Sharpe, max drawdown, and trade counts',
  candidates_json: 'Strategy entry signals evaluated each bar; hydrates the Candidates tab',
  candidates_parquet: 'Strategy entry signals evaluated each bar; hydrates the Candidates tab',
  equity_parquet: 'Portfolio value time series per run; used in run and strategy charts',
  orders_parquet: 'Broker orders submitted during each run',
  trades_parquet: 'Closed trade records with PnL, size, and exit reason',
  rejections_parquet: 'Filter and auditor reasons a signal was blocked',
  labels_parquet: 'Risk-model outcome labels for candidate events',
  features_parquet: 'Risk-model feature vectors at candidate events',
}

type ArtifactDescriptionSource = {
  kind: string
  description?: string | null
}

export function resolveArtifactDescription(artifact: ArtifactDescriptionSource): string {
  if (artifact.description) {
    return artifact.description
  }
  return ARTIFACT_DESCRIPTIONS[artifact.kind] ?? 'Auxiliary backtest output file'
}
