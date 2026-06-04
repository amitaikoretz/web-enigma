import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const fetchBacktestsMock = vi.hoisted(() => vi.fn())
const createRiskModelMock = vi.hoisted(() => vi.fn())
const createReturnForecastModelMock = vi.hoisted(() => vi.fn())
const deleteBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestForceMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  deleteBacktest: deleteBacktestMock,
  fetchBacktests: fetchBacktestsMock,
  retryBacktest: retryBacktestMock,
  retryBacktestForce: retryBacktestForceMock,
}))

vi.mock('../api/riskModels', () => ({
  createRiskModel: createRiskModelMock,
}))

vi.mock('../api/returnForecastModels', () => ({
  createReturnForecastModel: createReturnForecastModelMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
      backtest_defaults: {
        results_table_columns: ['status'],
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { BacktestsListPage } from './BacktestsListPage'

describe('BacktestsListPage model launch modal', () => {
  it('launches a risk model from the pre-launch modal', async () => {
    fetchBacktestsMock.mockResolvedValue({
      items: [
        {
          id: 'bt-1',
          created_at: '2026-06-01T12:00:00.000Z',
          updated_at: '2026-06-01T12:01:00.000Z',
          status: 'succeeded',
          selection: null,
        },
      ],
      total: 1,
    })
    createRiskModelMock.mockResolvedValue({
      group_id: 'rm-1',
      status: 'running',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
    })

    render(
      <MemoryRouter>
        <BacktestsListPage />
      </MemoryRouter>,
    )

    await screen.findByText('bt-1')
    fireEvent.click(screen.getByLabelText('Select backtest bt-1'))
    fireEvent.click(screen.getByRole('button', { name: /train risk model/i }))
    expect(screen.getByText('Train risk model')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/random seed/i), { target: { value: '13' } })
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    await waitFor(() =>
      expect(createRiskModelMock).toHaveBeenCalledWith({
        backtest_ids: ['bt-1'],
        targets: [
          { target_key: 'stop_prob', task_type: 'classification' },
          { target_key: 'mae', task_type: 'regression' },
        ],
        dataset_config: {},
        train_config: { random_seed: 13 },
      }),
    )
    expect(await screen.findByText('Model launched')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /risk model rm-1/i })).toHaveAttribute('href', '/models/risk/rm-1')
  })

  it('launches a return forecast model from the pre-launch modal', async () => {
    fetchBacktestsMock.mockResolvedValue({
      items: [
        {
          id: 'bt-2',
          created_at: '2026-06-01T12:00:00.000Z',
          updated_at: '2026-06-01T12:01:00.000Z',
          status: 'succeeded',
          selection: null,
        },
      ],
      total: 1,
    })
    createReturnForecastModelMock.mockResolvedValue({
      group_id: 'rf-1',
      status: 'running',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
    })

    render(
      <MemoryRouter>
        <BacktestsListPage />
      </MemoryRouter>,
    )

    await screen.findByText('bt-2')
    fireEvent.click(screen.getByLabelText('Select backtest bt-2'))
    fireEvent.click(screen.getByRole('button', { name: /train return forecast/i }))
    expect(screen.getByText('Train return forecast model')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/random seed/i), { target: { value: '21' } })
    fireEvent.change(screen.getByLabelText(/lookback bars/i), { target: { value: '90' } })
    fireEvent.change(screen.getByLabelText(/horizon bars/i), { target: { value: '8' } })
    fireEvent.click(screen.getByLabelText(/allow short signals/i))
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    await waitFor(() =>
      expect(createReturnForecastModelMock).toHaveBeenCalledWith({
        backtest_ids: ['bt-2'],
        targets: [{ target_key: 'forecast_return', task_type: 'regression' }],
        dataset_config: {},
        train_config: {
          random_seed: 21,
          lookback_bars: 90,
          horizon_bars: 8,
          allow_short: false,
        },
      }),
    )
    expect(await screen.findByText('Model launched')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /return forecast model rf-1/i })).toHaveAttribute(
      'href',
      '/models/returns/rf-1',
    )
  })
})
