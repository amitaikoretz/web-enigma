import { describe, expect, it } from 'vitest'

import { buildDatasetCopySnippet } from './datasetCopy'

describe('buildDatasetCopySnippet', () => {
  it('uses the provided manifest path when available', () => {
    const snippet = buildDatasetCopySnippet({
      manifestPath: '/tmp/datasets/aapl.manifest.json',
      datasetParquetPath: '/tmp/datasets/aapl.parquet',
    })

    expect(snippet).toContain('manifest_path = Path("/tmp/datasets/aapl.manifest.json")')
    expect(snippet).toContain('from app.risk.dataset.reader import RiskDatasetReader')
    expect(snippet).toContain('print(f"rows: {len(dataset):,}")')
  })

  it('derives a manifest path from the parquet path when needed', () => {
    const snippet = buildDatasetCopySnippet({
      manifestPath: null,
      datasetParquetPath: '/tmp/datasets/aapl.parquet',
    })

    expect(snippet).toContain('manifest_path = Path("/tmp/datasets/aapl.manifest.json")')
  })
})
