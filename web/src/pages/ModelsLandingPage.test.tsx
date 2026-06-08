import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const navigateMock = vi.hoisted(() => vi.fn())
const fetchRiskModelsMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelStatusMock = vi.hoisted(() => vi.fn())
const deleteRiskModelMock = vi.hoisted(() => vi.fn())
const deleteReturnForecastModelMock = vi.hoisted(() => vi.fn())
const deleteDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/riskModels', () => ({
  fetchRiskModels: fetchRiskModelsMock,
  fetchRiskModelStatus: vi.fn(),
  fetchRiskModelWorkflowErrors: vi.fn(),
  deleteRiskModel: deleteRiskModelMock,
  retryRiskModel: vi.fn(),
}))

vi.mock('../api/returnForecastModels', () => ({
  fetchReturnForecastModels: fetchReturnForecastModelsMock,
  fetchReturnForecastModelStatus: vi.fn(async () => ({
    group_id: 'return-1',
    status: 'running',
    argo_phase: 'Running',
  })),
  fetchReturnForecastModelWorkflowErrors: vi.fn(),
  deleteReturnForecastModel: deleteReturnForecastModelMock,
  retryReturnForecastModel: vi.fn(),
}))

vi.mock('../api/dailyIndexForecastModels', () => ({
  fetchDailyIndexForecastModels: fetchDailyIndexForecastModelsMock,
  fetchDailyIndexForecastModelStatus: fetchDailyIndexForecastModelStatusMock,
  fetchDailyIndexForecastModelWorkflowErrors: vi.fn(),
  deleteDailyIndexForecastModel: deleteDailyIndexForecastModelMock,
  retryDailyIndexForecastModel: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { ModelsLandingPage } from './ModelsLandingPage'

describe('ModelsLandingPage', () => {
  it('renders all model families in one list and filters by family', async () => {
    fetchDailyIndexForecastModelStatusMock.mockResolvedValue({
      group_id: 'daily-1',
      status: 'running',
      argo_phase: 'Running',
      progress_pct: 37,
    })
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'risk-1',
        name: 'Momentum Risk v1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['bt-1'],
        dataset_ids: [],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        summary_metrics: null,
        artifact_dir: '/tmp/risk-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
    fetchReturnForecastModelsMock.mockResolvedValue([
      {
        group_id: 'return-1',
        name: 'Short Horizon Forecast',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'running',
        backtest_ids: ['bt-2'],
        dataset_ids: [],
        targets: ['forecast_return'],
        targets_total: 4,
        targets_done: 2,
        summary_metrics: null,
        artifact_dir: '/tmp/return-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
    fetchDailyIndexForecastModelsMock.mockResolvedValue([
      {
        group_id: 'daily-1',
        feature_run_id: 'fr-1',
        name: 'Daily Alpha',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'running',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        targets: ['forecast_return'],
        targets_total: 4,
        targets_done: 1,
        summary_metrics: null,
        artifact_dir: '/tmp/daily-1',
        feature_run_artifact_dir: '/tmp/daily-run-1',
      },
    ])

    render(
      <MemoryRouter initialEntries={['/models']}>
        <Routes>
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Momentum Risk v1')).toBeInTheDocument()
    expect(screen.getByText('Short Horizon Forecast')).toBeInTheDocument()
    expect(screen.getByText('Daily Alpha')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^status$/i })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /^progress$/i })).not.toBeInTheDocument()

    const riskRow = screen.getByText('Momentum Risk v1').closest('tr')
    expect(riskRow).not.toBeNull()
    if (!riskRow) {
      throw new Error('Risk model row was not rendered')
    }
    expect(within(riskRow).getByText('succeeded')).toBeInTheDocument()
    expect(within(riskRow).queryByRole('progressbar')).not.toBeInTheDocument()
    expect(within(riskRow).queryByText('1/1')).not.toBeInTheDocument()

    const runningRow = screen.getByText('Short Horizon Forecast').closest('tr')
    expect(runningRow).not.toBeNull()
    if (!runningRow) {
      throw new Error('Running model row was not rendered')
    }
    expect(within(runningRow).queryByText('running')).not.toBeInTheDocument()
    expect(within(runningRow).getByRole('progressbar')).toBeInTheDocument()
    expect(within(runningRow).getByText('2/4')).toBeInTheDocument()

    const dailyRow = screen.getByText('Daily Alpha').closest('tr')
    expect(dailyRow).not.toBeNull()
    if (!dailyRow) {
      throw new Error('Daily Index model row was not rendered')
    }
    expect(within(dailyRow).getByRole('progressbar')).toBeInTheDocument()
    expect(within(dailyRow).getByText('37% complete')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /risk/i }))

    await waitFor(() => expect(screen.queryByText('Short Horizon Forecast')).not.toBeInTheDocument())
    expect(screen.getByText('Momentum Risk v1')).toBeInTheDocument()
  })

  it('opens the training wizard from the models header', async () => {
    navigateMock.mockReset()
    fetchRiskModelsMock.mockResolvedValue([])
    fetchReturnForecastModelsMock.mockResolvedValue([])
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])

    render(
      <MemoryRouter initialEntries={['/models?family=risk']}>
        <Routes>
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click((await screen.findAllByRole('button', { name: /train model/i }))[0])

    expect(navigateMock).toHaveBeenCalledWith('/models/risk/new')
  })

  it('supports bulk deleting selected models', async () => {
    fetchRiskModelsMock.mockResolvedValue([
      {
        group_id: 'risk-1',
        name: 'Momentum Risk v1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['bt-1'],
        dataset_ids: [],
        targets: ['stop_prob'],
        targets_total: 1,
        targets_done: 1,
        summary_metrics: null,
        artifact_dir: '/tmp/risk-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
    fetchReturnForecastModelsMock.mockResolvedValue([
      {
        group_id: 'return-1',
        name: 'Short Horizon Forecast',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        backtest_ids: ['bt-2'],
        dataset_ids: [],
        targets: ['forecast_return'],
        targets_total: 1,
        targets_done: 1,
        summary_metrics: null,
        artifact_dir: '/tmp/return-1',
        training_start_date: '2024-01-01',
        training_end_date: '2024-01-10',
      },
    ])
    fetchDailyIndexForecastModelsMock.mockResolvedValue([
      {
        group_id: 'daily-1',
        feature_run_id: 'fr-1',
        name: 'Daily Alpha',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'succeeded',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        targets: ['forecast_return'],
        targets_total: 1,
        targets_done: 1,
        summary_metrics: null,
        artifact_dir: '/tmp/daily-1',
        feature_run_artifact_dir: '/tmp/daily-run-1',
      },
    ])

    deleteRiskModelMock.mockResolvedValue(undefined)
    deleteReturnForecastModelMock.mockResolvedValue(undefined)
    deleteDailyIndexForecastModelMock.mockResolvedValue(undefined)

    render(
      <MemoryRouter initialEntries={['/models']}>
        <Routes>
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('Momentum Risk v1')
    expect(screen.getAllByRole('button', { name: /delete selected/i })[0]).toBeDisabled()
    expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(1)
  })
})
