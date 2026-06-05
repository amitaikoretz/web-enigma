import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchRiskModelsMock = vi.hoisted(() => vi.fn())
const fetchRiskModelStatusMock = vi.hoisted(() => vi.fn())
const fetchRiskModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const retryRiskModelMock = vi.hoisted(() => vi.fn())
const deleteRiskModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/riskModels', () => ({
  deleteRiskModel: deleteRiskModelMock,
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
  it('navigates to the detail route when a row is clicked', async () => {
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'g-1',
        name: 'Momentum Risk v1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['b1'],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/risk-models/g-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])

    render(
      <MemoryRouter initialEntries={['/models/risk']}>
        <Routes>
          <Route path="/models/risk" element={<RiskModelsListPage />} />
          <Route path="/models/risk/:groupId" element={<div>risk model detail route</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Momentum Risk v1')).toBeInTheDocument())
    expect(screen.getByText('g-1')).toBeInTheDocument()
    expect(screen.getByText('2024-01-01 to 2024-01-10')).toBeInTheDocument()
    fireEvent.click(screen.getByText('g-1'))

    await waitFor(() => expect(screen.getByText('risk model detail route')).toBeInTheDocument())
  })

  it('opens workflow errors from the failed-row action', async () => {
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'g-failed',
        name: 'Momentum Risk v1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'failed',
        backtest_ids: ['b1'],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/risk-models/g-failed',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
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

    render(
      <MemoryRouter initialEntries={['/models/risk']}>
        <Routes>
          <Route path="/models/risk" element={<RiskModelsListPage />} />
          <Route path="/models/risk/:groupId" element={<div>risk model detail route</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('g-failed')).toBeInTheDocument())
    const row = screen.getByText('g-failed').closest('tr')
    expect(row).not.toBeNull()

    const workflowErrorsButton = within(row!).getByRole('button', { name: /workflow errors/i })
    fireEvent.click(workflowErrorsButton)

    await waitFor(() => expect(fetchRiskModelWorkflowErrorsMock).toHaveBeenCalledWith('g-failed'))
    expect(screen.getByText('Workflow errors')).toBeInTheDocument()
    expect(screen.getByText('RuntimeError: boom')).toBeInTheDocument()
    expect(screen.getByText('/tmp/train.py:42')).toBeInTheDocument()
  })
})
