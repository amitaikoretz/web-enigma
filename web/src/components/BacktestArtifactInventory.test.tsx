import '@testing-library/jest-dom/vitest'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import type { BacktestArtifactEntry } from '../types/backtests'
import { buildSidecarCopySnippet } from '../utils/backtestArtifactCopy'
import { BacktestArtifactInventory } from './BacktestArtifactInventory'

function makeArtifact(overrides: Partial<BacktestArtifactEntry>): BacktestArtifactEntry {
  return {
    kind: 'report_parquet',
    label: 'Run summaries',
    description: 'Per-run headline metrics',
    format: 'parquet',
    role: 'sidecar',
    path: '/tmp/backtests/example/report.parquet',
    size_bytes: 1024,
    ...overrides,
  }
}

describe('buildSidecarCopySnippet', () => {
  it('builds a parquet snippet that validates the first row with the right model', () => {
    const snippet = buildSidecarCopySnippet(
      makeArtifact({
        kind: 'features_parquet',
        label: 'Feature snapshots',
        format: 'parquet',
        path: '/tmp/backtests/run-1.features.parquet',
      }),
    )

    expect(snippet).toContain('from app.output.records import FeatureSnapshotRecord')
    expect(snippet).toContain('frame = pd.read_parquet(artifact_path)')
    expect(snippet).toContain('record = FeatureSnapshotRecord.model_validate(row_data)')
    expect(snippet).toContain('explain_record(FeatureSnapshotRecord, record)')
  })

  it('builds a json snippet that validates the first record with the right model', () => {
    const snippet = buildSidecarCopySnippet(
      makeArtifact({
        kind: 'candidates_json',
        label: 'Entry candidates (JSON)',
        format: 'json',
        path: '/tmp/backtests/run-1.candidates.json',
      }),
    )

    expect(snippet).toContain('from app.output.records import CandidateRecord')
    expect(snippet).toContain('payload = json.loads(artifact_path.read_text())')
    expect(snippet).toContain('record = CandidateRecord.model_validate(row_data)')
    expect(snippet).toContain('explain_record(CandidateRecord, record)')
  })

  it('builds a report summary snippet that uses a dedicated Pydantic row model', () => {
    const snippet = buildSidecarCopySnippet(
      makeArtifact({
        kind: 'report_parquet',
        label: 'Run summaries',
        format: 'parquet',
        path: '/tmp/backtests/run-1.parquet',
      }),
    )

    expect(snippet).toContain('from app.output.records import ReportSummaryRecord')
    expect(snippet).toContain('record = ReportSummaryRecord.model_validate(row_data)')
    expect(snippet).toContain('explain_record(ReportSummaryRecord, record)')
  })
})

describe('BacktestArtifactInventory', () => {
  beforeEach(() => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows a copy button only for sidecar rows and copies the generated snippet', async () => {
    const artifacts: BacktestArtifactEntry[] = [
      {
        kind: 'report_json',
        label: 'Report summary',
        description: 'Slim JSON index',
        format: 'json',
        role: 'primary',
        path: '/tmp/backtests/example/report.json',
        size_bytes: 4096,
      },
      makeArtifact({
        kind: 'features_parquet',
        label: 'Feature snapshots',
        description: 'Feature vectors for each candidate',
        format: 'parquet',
        path: '/tmp/backtests/example/features.parquet',
      }),
    ]

    render(<BacktestArtifactInventory artifacts={artifacts} />)

    const table = screen.getByText('Feature snapshots').closest('table')
    expect(table).not.toBeNull()
    if (!table) {
      return
    }
    expect(within(table).getAllByRole('button', { name: /copy python snippet/i })).toHaveLength(1)

    fireEvent.click(within(table).getByRole('button', { name: /copy python snippet/i }))

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('FeatureSnapshotRecord.model_validate(row_data)'),
    )
    expect(
      await within(table).findByRole('button', { name: /copied python snippet/i }),
    ).toBeInTheDocument()
  })
})
