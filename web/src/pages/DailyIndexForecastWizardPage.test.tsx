import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const createDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const fetchDatasetDetailMock = vi.hoisted(() => vi.fn())
const fetchDatasetsMock = vi.hoisted(() => vi.fn())
const fetchRiskModelsMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelsMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const retryDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const deleteDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  fetchDatasetDetail: fetchDatasetDetailMock,
  fetchDatasets: fetchDatasetsMock,
  deleteDataset: vi.fn(),
}))

vi.mock('../api/riskModels', () => ({
  fetchRiskModels: fetchRiskModelsMock,
  fetchRiskModelStatus: vi.fn(),
  fetchRiskModelWorkflowErrors: vi.fn(),
  deleteRiskModel: vi.fn(),
  retryRiskModel: vi.fn(),
}))

vi.mock('../api/returnForecastModels', () => ({
  fetchReturnForecastModels: fetchReturnForecastModelsMock,
  fetchReturnForecastModelStatus: vi.fn(),
  fetchReturnForecastModelWorkflowErrors: vi.fn(),
  deleteReturnForecastModel: vi.fn(),
  retryReturnForecastModel: vi.fn(),
}))

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

import { DailyIndexForecastWizardPage } from './DailyIndexForecastWizardPage'
import { DailyIndexForecastModelsListPage } from './DailyIndexForecastModelsListPage'
import { ModelsLandingPage } from './ModelsLandingPage'

function getVisibleLaunchButton(): HTMLElement {
  const buttons = Array.from(document.querySelectorAll('[data-testid="daily-index-launch-forecast"]')) as HTMLElement[]
  const visible = buttons.find((button) => !button.closest('[aria-hidden="true"]'))
  if (!visible) {
    throw new Error('Daily Index launch button not found')
  }
  return visible
}

describe('DailyIndexForecastWizardPage launch flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    })
    fetchDatasetsMock.mockResolvedValue({
      items: [
        {
          id: 'ds-1',
          name: 'My dataset',
          symbol: 'AAPL',
          provider: 'alpaca',
          resolution: '5m',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'completed',
          argo_namespace: null,
          argo_workflow_name: null,
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: '/tmp/datasets/aapl.parquet',
          manifest_path: '/tmp/datasets/aapl.manifest.json',
          options_parquet_path: null,
          options_manifest_path: null,
          error_message: null,
          progress_pct: 100,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    })
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-1',
        name: 'My dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '5m',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'completed',
        argo_namespace: null,
        argo_workflow_name: null,
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: '/tmp/datasets/aapl.parquet',
        manifest_path: '/tmp/datasets/aapl.manifest.json',
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: null,
        progress_pct: 100,
      },
      symbol_options: ['AAPL', 'MSFT'],
    })
    fetchRiskModelsMock.mockResolvedValue([])
    fetchReturnForecastModelsMock.mockResolvedValue([])
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
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('combobox', { name: /data source/i })).not.toBeDisabled()
    expect(screen.getByLabelText(/^interval$/i)).not.toBeDisabled()
    expect(screen.getByLabelText(/^feed$/i)).not.toBeDisabled()

    fireEvent.click(screen.getByTestId('daily-index-launch-forecast'))

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
    expect(screen.getByRole('link', { name: 'di-1' })).toHaveAttribute('href', '/models/daily-index/di-1')
  })

  it('shows a symbol dropdown for dataset-backed launches and submits the selected symbol', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])
    createDailyIndexForecastModelMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      status: 'running',
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/models/daily-index/new',
            state: {
              sourceKind: 'dataset',
              sourceIds: ['ds-1'],
              selectedCount: 1,
              selectionLabel: 'datasets',
              dailyIndexDatasetSource: {
                symbol: 'AAPL',
                start_date: '2026-05-01',
                end_date: '2026-06-01',
              },
            },
          },
        ]}
      >
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const datasetModeSwitches = await screen.findAllByRole('switch', { name: /use existing dataset/i })
    await waitFor(() => expect(datasetModeSwitches[0]).toBeChecked())
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: /existing dataset/i })).toHaveValue(
        'My dataset - AAPL - 2026-05-01 to 2026-06-01',
      ),
    )
    expect(screen.getByRole('combobox', { name: /data source/i })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByLabelText(/^interval$/i)).toBeDisabled()
    expect(screen.getByLabelText(/^feed$/i)).toBeDisabled()
    expect(screen.queryByLabelText(/^benchmark symbol$/i)).not.toBeInTheDocument()

    const symbolSelect = screen.getByRole('combobox', { name: /^symbol$/i })
    expect(symbolSelect).toHaveTextContent('AAPL')
    fireEvent.mouseDown(symbolSelect)
    fireEvent.click(await screen.findByRole('option', { name: 'MSFT' }))
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())

    fireEvent.click(screen.getByTestId('daily-index-launch-forecast'))

    await waitFor(() =>
      expect(createDailyIndexForecastModelMock).toHaveBeenCalledWith(
        expect.objectContaining({
          universe: expect.objectContaining({
            symbols: [
              expect.objectContaining({
                symbol: 'MSFT',
                data: expect.objectContaining({
                  type: 'alpaca',
                  symbol: 'MSFT',
                  interval: '5m',
                  feed: 'iex',
                }),
              }),
            ],
            start_date: '2026-05-01',
            end_date: '2026-06-01',
            benchmark: expect.objectContaining({
              symbol: 'MSFT',
              data: expect.objectContaining({
                symbol: 'MSFT',
              }),
            }),
          }),
        }),
      ),
    )
  })

  it('shows an empty-state message when there are no completed datasets to choose from', async () => {
    fetchDatasetsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 1,
    })
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/models/daily-index/new',
            state: {
              sourceKind: 'dataset',
              sourceIds: ['ds-1'],
              selectedCount: 1,
              selectionLabel: 'datasets',
              dailyIndexDatasetSource: {
                symbol: 'AAPL',
                start_date: '2026-05-01',
                end_date: '2026-06-01',
              },
            },
          },
        ]}
      >
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText(/launch a dataset job first, then return here/i)).toBeInTheDocument()
  })

  it('shows a loading state while existing datasets are being fetched', async () => {
    fetchDatasetsMock.mockImplementation(
      () =>
        new Promise(() => {
          // Intentionally never resolves to keep the loading state visible.
        }),
    )
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/models/daily-index/new',
            state: {
              sourceKind: 'dataset',
              sourceIds: ['ds-1'],
              selectedCount: 1,
              selectionLabel: 'datasets',
              dailyIndexDatasetSource: {
                symbol: 'AAPL',
                start_date: '2026-05-01',
                end_date: '2026-06-01',
              },
            },
          },
        ]}
      >
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText(/loading completed datasets/i)).toBeInTheDocument()
  })

  it.skip('shows a launch modal on the list page after a failed launch', async () => {
    fetchDailyIndexForecastModelsMock.mockResolvedValue([])
    createDailyIndexForecastModelMock.mockRejectedValue(new Error('Argo submit failed'))

    render(
      <MemoryRouter initialEntries={['/models/daily-index/new']}>
        <Routes>
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(getVisibleLaunchButton())

    await waitFor(() => expect(createDailyIndexForecastModelMock).toHaveBeenCalled())

    expect(await screen.findByText('Daily Index Forecast launch failed')).toBeInTheDocument()
    expect(screen.getByText('Argo submit failed')).toBeInTheDocument()
  })
})
