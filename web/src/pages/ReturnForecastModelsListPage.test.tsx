import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchReturnForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const retryReturnForecastModelMock = vi.hoisted(() => vi.fn())
const deleteReturnForecastModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/returnForecastModels', () => ({
  deleteReturnForecastModel: deleteReturnForecastModelMock,
  fetchReturnForecastModelStatus: fetchReturnForecastModelStatusMock,
  fetchReturnForecastModels: fetchReturnForecastModelsMock,
  fetchReturnForecastModelWorkflowErrors: fetchReturnForecastModelWorkflowErrorsMock,
  retryReturnForecastModel: retryReturnForecastModelMock,
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

import { ReturnForecastModelsListPage } from './ReturnForecastModelsListPage'

describe('ReturnForecastModelsListPage', () => {
  it('navigates to the detail route when a row is clicked', async () => {
    fetchReturnForecastModelsMock.mockResolvedValue([
      {
        group_id: 'rf-1',
        name: 'Short Horizon Forecast',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['b1'],
        targets: ['forecast_return'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/return-forecast-models/rf-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])

    render(
      <MemoryRouter initialEntries={['/models/returns']}>
        <Routes>
          <Route path="/models/returns" element={<ReturnForecastModelsListPage />} />
          <Route path="/models/returns/:groupId" element={<div>return forecast model detail route</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Short Horizon Forecast')).toBeInTheDocument())
    expect(screen.getByText('rf-1')).toBeInTheDocument()
    expect(screen.getByText('2024-01-01 to 2024-01-10')).toBeInTheDocument()
    fireEvent.click(screen.getByText('rf-1'))

    await waitFor(() => expect(screen.getByText('return forecast model detail route')).toBeInTheDocument())
  })

  it('opens workflow errors from the failed-row action', async () => {
    fetchReturnForecastModelsMock.mockResolvedValue([
      {
        group_id: 'rf-failed',
        name: 'Short Horizon Forecast',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'failed',
        backtest_ids: ['b1'],
        targets: ['forecast_return'],
        targets_total: 1,
        targets_done: 1,
        artifact_dir: '/tmp/return-forecast-models/rf-failed',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
    fetchReturnForecastModelWorkflowErrorsMock.mockResolvedValue({
      group_id: 'rf-failed',
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
      <MemoryRouter initialEntries={['/models/returns']}>
        <Routes>
          <Route path="/models/returns" element={<ReturnForecastModelsListPage />} />
          <Route path="/models/returns/:groupId" element={<div>return forecast model detail route</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('rf-failed')).toBeInTheDocument())
    const row = screen.getByText('rf-failed').closest('tr')
    expect(row).not.toBeNull()

    const workflowErrorsButton = within(row!).getByRole('button', { name: /workflow errors/i })
    fireEvent.click(workflowErrorsButton)

    await waitFor(() => expect(fetchReturnForecastModelWorkflowErrorsMock).toHaveBeenCalledWith('rf-failed'))
    expect(screen.getByText('Workflow errors')).toBeInTheDocument()
    expect(screen.getByText('RuntimeError: boom')).toBeInTheDocument()
    expect(screen.getByText('/tmp/train.py:42')).toBeInTheDocument()
  })
})
