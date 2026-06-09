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

function deriveDatasetPath(manifestPath: string | null | undefined): string {
  const path = manifestPath?.trim()
  if (!path) {
    return '/path/to/dataset.parquet'
  }

  const derivedPath = path.replace(/\.manifest\.json$/i, '.parquet')
  return derivedPath === path ? `${path}.parquet` : derivedPath
}

export function buildDatasetCopySnippet({ manifestPath, datasetParquetPath }: DatasetCopySource): string {
  const resolvedDatasetPath = datasetParquetPath?.trim() || deriveDatasetPath(manifestPath)
  const datasetPathLiteral = pythonStringLiteral(resolvedDatasetPath)
  const resolvedManifestPath = manifestPath?.trim() || resolvedDatasetPath.replace(/\.parquet$/i, '.manifest.json')
  const manifestPathLiteral = pythonStringLiteral(resolvedManifestPath)

  return [
    'from pathlib import Path',
    '',
    'from app.datasets.reader import DatasetArtifactReader',
    '',
    `dataset_path = Path(${datasetPathLiteral})`,
    `manifest_path = Path(${manifestPathLiteral})`,
    'reader = DatasetArtifactReader.from_manifest_path(manifest_path, dataset_path=dataset_path)',
    'dataset = reader.load()',
    '',
    'if dataset.empty:',
    '    raise ValueError(f"{dataset_path} produced an empty dataset")',
    '',
    'print("Dataset artifact summary:")',
    'print(f"dataset_kind: {reader.manifest.dataset_kind}")',
    'print(f"dataset_id: {reader.manifest.dataset_id}")',
    'print(f"provider: {reader.manifest.provider}")',
    'print(f"resolution: {reader.manifest.resolution}")',
    'print(f"start_date: {reader.manifest.start_date}")',
    'print(f"end_date: {reader.manifest.end_date}")',
    'print(f"output_path: {reader.manifest.output_path}")',
    'print(f"chunk_count: {reader.chunk_count}")',
    'print(f"total_row_count: {reader.manifest.total_row_count:,}")',
    'print(f"total_size_bytes: {reader.manifest.total_size_bytes:,}")',
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
