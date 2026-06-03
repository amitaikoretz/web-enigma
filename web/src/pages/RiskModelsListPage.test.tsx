import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const fetchRiskModelsMock = vi.hoisted(() => vi.fn())
const fetchRiskModelStatusMock = vi.hoisted(() => vi.fn())
const fetchRiskModelDetailMock = vi.hoisted(() => vi.fn())
const fetchRiskModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const retryRiskModelMock = vi.hoisted(() => vi.fn())
const deleteRiskModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/riskModels', () => ({
  deleteRiskModel: deleteRiskModelMock,
  fetchRiskModelDetail: fetchRiskModelDetailMock,
  fetchRiskModelStatus: fetchRiskModelStatusMock,
  fetchRiskModels: fetchRiskModelsMock,
  fetchRiskModelWorkflowErrors: fetchRiskModelWorkflowErrorsMock,
  retryRiskModel: retryRiskModelMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
      },
    },
  }),
}))

import { RiskModelsListPage } from './RiskModelsListPage'

describe('RiskModelsListPage', () => {
  it('shows a retry action for failed models and submits the retry request', async () => {
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'g-failed',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'failed',
        backtest_ids: ['b1'],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/risk-models/g-failed',
      },
      {
        group_id: 'g-ok',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['b2'],
        targets: ['mae'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/risk-models/g-ok',
      },
    ])
    fetchRiskModelStatusMock.mockResolvedValue({ group_id: 'g-failed', status: 'failed' })
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-failed',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'failed',
      params: {},
      artifact_dir: '/tmp/risk-models/g-failed',
      sources: [],
      targets: [],
    })
    retryRiskModelMock.mockResolvedValue({
      group_id: 'g-retry',
      status: 'running',
    })

    render(<RiskModelsListPage />)

    await waitFor(() => expect(screen.getByText('g-failed')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /retry training/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retry training/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /retry training/i }))

    await waitFor(() => expect(retryRiskModelMock).toHaveBeenCalledWith('g-failed'))
  })

  it('opens workflow errors for a failed row and still opens details from the icon', async () => {
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'g-failed',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'failed',
        backtest_ids: ['b1'],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/risk-models/g-failed',
      },
    ])
    fetchRiskModelStatusMock.mockResolvedValue({ group_id: 'g-failed', status: 'failed' })
    fetchRiskModelWorkflowErrorsMock.mockResolvedValue({
      group_id: 'g-failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
      available: true,
      status_message: 'Loaded error details from the failed workflow step.',
      failed_node_name: 'train-stop',
      failed_template_name: 'train-stop',
      error_exception: 'RuntimeError: boom',
      error_code_location: '/tmp/train.py:42',
      error_call_stack: ['/tmp/train.py:42', '/tmp/train.py:13'],
      error_traceback: 'Traceback (most recent call last):\nboom',
    })
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-failed',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'failed',
      params: {},
      artifact_dir: '/tmp/risk-models/g-failed',
      sources: [],
      targets: [],
    })

    render(<RiskModelsListPage />)

    await waitFor(() => expect(screen.getByText('g-failed')).toBeInTheDocument())
    const failedRow = screen.getAllByText('g-failed')[0].closest('tr')
    expect(failedRow).not.toBeNull()
    fireEvent.click(failedRow!)

    await waitFor(() => expect(fetchRiskModelWorkflowErrorsMock).toHaveBeenCalledWith('g-failed'))
    expect(screen.getByText('Workflow errors')).toBeInTheDocument()
    expect(screen.getByText('RuntimeError: boom')).toBeInTheDocument()
    expect(screen.getByText('/tmp/train.py:42')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    await waitFor(() =>
      expect(screen.queryByText('Workflow errors')).not.toBeInTheDocument(),
    )

    const detailsButton = within(failedRow!).getByRole('button', { name: /open details/i })
    fireEvent.click(detailsButton)
    await waitFor(() => expect(fetchRiskModelDetailMock).toHaveBeenCalledWith('g-failed'))
    expect(screen.getByRole('dialog', { name: /risk model g-failed/i })).toBeInTheDocument()
  })
})
