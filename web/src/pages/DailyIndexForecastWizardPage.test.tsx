import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { defaultPlatformSettings } from '../settings/defaults'

const createDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const retryDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const deleteDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/dailyIndexForecastModels', () => ({
  createDailyIndexForecastModel: createDailyIndexForecastModelMock,
  deleteDailyIndexForecastModel: deleteDailyIndexForecastModelMock,
  fetchDailyIndexForecastModels: fetchDailyIndexForecastModelsMock,
  fetchDailyIndexForecastModelStatus: fetchDailyIndexForecastModelStatusMock,
  fetchDailyIndexForecastModelWorkflowErrors: fetchDailyIndexForecastModelWorkflowErrorsMock,
  retryDailyIndexForecastModel: retryDailyIndexForecastModelMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      ...defaultPlatformSettings,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        auto_refresh_interval_seconds: 60,
      },
    },
  }),
}))

import { DailyIndexForecastModelsListPage } from './DailyIndexForecastModelsListPage'
import { DailyIndexForecastWizardPage } from './DailyIndexForecastWizardPage'

describe('DailyIndexForecastWizardPage launch flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('shows a launch modal on the list page after a successful launch', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])
    fetchDailyIndexForecastModelStatusMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      status: 'running',
    })
    createDailyIndexForecastModelMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      status: 'running',
    })

    render(
      <MemoryRouter initialEntries={['/models/daily-index/new']}>
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /launch forecast/i }))

    await waitFor(() =>
      expect(createDailyIndexForecastModelMock).toHaveBeenCalledWith(
        expect.objectContaining({
          universe: expect.objectContaining({
            symbols: [
              expect.objectContaining({
                symbol: 'SPY',
              }),
            ],
          }),
        }),
      ),
    )

    expect(await screen.findByText('Daily Index Forecast launched')).toBeInTheDocument()
    expect(screen.getByText('Daily Index Forecast launch submitted successfully.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /forecast di-1/i })).toHaveAttribute('href', '/models/daily-index/di-1')
  })

  it('shows a launch modal on the list page after a failed launch', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])
    createDailyIndexForecastModelMock.mockRejectedValue(new Error('Argo submit failed'))

    render(
      <MemoryRouter initialEntries={['/models/daily-index/new']}>
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /launch forecast/i }))

    await waitFor(() => expect(createDailyIndexForecastModelMock).toHaveBeenCalled())

    expect(await screen.findByText('Daily Index Forecast launch failed')).toBeInTheDocument()
    expect(screen.getByText('Argo submit failed')).toBeInTheDocument()
  })

  it('confirms retry submission and shows a success modal', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([
      {
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        created_at: '2026-06-05T10:00:00.000Z',
        updated_at: '2026-06-05T10:00:00.000Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        targets: [],
        targets_total: 0,
        targets_done: 0,
        summary_metrics: null,
        artifact_dir: '/tmp/group',
        feature_run_artifact_dir: '/tmp/feature',
      },
    ])
    retryDailyIndexForecastModelMock.mockResolvedValue({
      group_id: 'di-2',
      feature_run_id: 'fr-2',
      status: 'running',
    })

    render(
      <MemoryRouter initialEntries={['/models/daily-index']}>
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const row = await screen.findByRole('row', {
      name: /di-1 spy failed 1\/1\/2024 to 1\/31\/2024 09:45/i,
    })
    fireEvent.click(within(row).getAllByRole('button')[2])
    expect(screen.getByText('Retry Daily Index Forecast di-1?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^retry$/i }))

    await waitFor(() => expect(retryDailyIndexForecastModelMock).toHaveBeenCalledWith('di-1'))

    expect(await screen.findByText('Daily Index Forecast retry submitted')).toBeInTheDocument()
    expect(screen.getByText('Daily Index Forecast retry submitted successfully.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /forecast di-2/i })).toHaveAttribute('href', '/models/daily-index/di-2')
  })

  it('confirms retry submission and shows the Argo error', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([
      {
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        created_at: '2026-06-05T10:00:00.000Z',
        updated_at: '2026-06-05T10:00:00.000Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        targets: [],
        targets_total: 0,
        targets_done: 0,
        summary_metrics: null,
        artifact_dir: '/tmp/group',
        feature_run_artifact_dir: '/tmp/feature',
      },
    ])
    retryDailyIndexForecastModelMock.mockRejectedValue(new Error('Failed to submit Argo workflow: 400 missing group-id'))

    render(
      <MemoryRouter initialEntries={['/models/daily-index']}>
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const row = await screen.findByRole('row', {
      name: /di-1 spy failed 1\/1\/2024 to 1\/31\/2024 09:45/i,
    })
    fireEvent.click(within(row).getAllByRole('button')[2])
    fireEvent.click(screen.getByRole('button', { name: /^retry$/i }))

    await waitFor(() => expect(retryDailyIndexForecastModelMock).toHaveBeenCalledWith('di-1'))

    expect(await screen.findByText('Daily Index Forecast retry failed')).toBeInTheDocument()
    expect(screen.getByText('Failed to submit Argo workflow: 400 missing group-id')).toBeInTheDocument()
  })
})
