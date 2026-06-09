type DatasetCopySource = {
  manifestPath?: string | null
  datasetParquetPath?: string | null
}

function escapePythonString(value: string): string {
  return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')
}

function pythonStringLiteral(value: string): string {
  return `"${escapePythonString(value)}"`
}

function deriveManifestPath(datasetParquetPath: string | null | undefined): string {
  const parquetPath = datasetParquetPath?.trim()
  if (!parquetPath) {
    return '/path/to/dataset.manifest.json'
  }

  const derivedPath = parquetPath.replace(/\.parquet$/i, '.manifest.json')
  return derivedPath === parquetPath ? `${parquetPath}.manifest.json` : derivedPath
}

export function buildDatasetCopySnippet({ manifestPath, datasetParquetPath }: DatasetCopySource): string {
  const resolvedManifestPath = manifestPath?.trim() || deriveManifestPath(datasetParquetPath)
  const manifestPathLiteral = pythonStringLiteral(resolvedManifestPath)

  return [
    'from pathlib import Path',
    '',
    'from app.risk.dataset.reader import RiskDatasetReader',
    '',
    `manifest_path = Path(${manifestPathLiteral})`,
    'reader = RiskDatasetReader.from_manifest_path(manifest_path)',
    'dataset = reader.load()',
    '',
    'if dataset.empty:',
    '    raise ValueError(f"{manifest_path} produced an empty dataset")',
    '',
    'print("Manifest summary:")',
    'print(f"generated_at: {reader.manifest.generated_at}")',
    'print(f"dataset_version: {reader.manifest.dataset_version}")',
    'print(f"joined_rows: {reader.manifest.joined_rows:,}")',
    'print(f"chunk_count: {reader.chunk_count}")',
    'print(f"primary_split_keys: {reader.primary_split_keys}")',
    'print(f"fallback_split_keys: {reader.fallback_split_keys}")',
    'print()',
    'print("Basic stats:")',
    'print(f"rows: {len(dataset):,}")',
    'print(f"columns: {len(dataset.columns):,}")',
    'print()',
    'print("Column dtypes:")',
    'print(dataset.dtypes.astype(str).to_string())',
    'print()',
    'print("Null counts (top 20):")',
    'print(dataset.isna().sum().sort_values(ascending=False).head(20).to_string())',
    'print()',
    'print("Head:")',
    'print(dataset.head(5).to_string(index=False))',
  ].join('\n')
}
