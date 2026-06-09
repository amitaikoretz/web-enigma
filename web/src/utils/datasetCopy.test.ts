import { describe, expect, it } from 'vitest'

import { buildDatasetCopySnippet } from './datasetCopy'

describe('buildDatasetCopySnippet', () => {
  it('uses the provided dataset path when available', () => {
    const snippet = buildDatasetCopySnippet({
      manifestPath: '/tmp/datasets/aapl.manifest.json',
      datasetParquetPath: '/tmp/datasets/aapl.parquet',
    })

    expect(snippet).toContain('dataset_path = Path("/tmp/datasets/aapl.parquet")')
    expect(snippet).toContain('manifest_path = Path("/tmp/datasets/aapl.manifest.json")')
    expect(snippet).toContain('from app.datasets.reader import DatasetArtifactReader')
    expect(snippet).toContain('print(f"rows: {len(dataset):,}")')
  })

  it('derives a dataset path from the parquet path when needed', () => {
    const snippet = buildDatasetCopySnippet({
      manifestPath: null,
      datasetParquetPath: '/tmp/datasets/aapl.parquet',
    })

    expect(snippet).toContain('dataset_path = Path("/tmp/datasets/aapl.parquet")')
  })

  it('derives a parquet path from the manifest path when needed', () => {
    const snippet = buildDatasetCopySnippet({
      manifestPath: '/tmp/datasets/aapl.manifest.json',
      datasetParquetPath: null,
    })

    expect(snippet).toContain('dataset_path = Path("/tmp/datasets/aapl.parquet")')
  })
})
