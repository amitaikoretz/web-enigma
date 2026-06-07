import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const fetchDatasetsMock = vi.hoisted(() => vi.fn())
const createRiskModelMock = vi.hoisted(() => vi.fn())
const createReturnForecastModelMock = vi.hoisted(() => vi.fn())
const createDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const deleteDatasetMock = vi.hoisted(() => vi.fn())
const fetchPlatformSettingsMock = vi.hoisted(() => vi.fn())
const loadAppearanceSettingsMock = vi.hoisted(() => vi.fn())
const saveAppearanceSettingsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  deleteDataset: deleteDatasetMock,
  fetchDatasets: fetchDatasetsMock,
}))

vi.mock('../api/riskModels', () => ({
  createRiskModel: createRiskModelMock,
}))

vi.mock('../api/returnForecastModels', () => ({
  createReturnForecastModel: createReturnForecastModelMock,
}))

vi.mock('../api/dailyIndexForecastModels', () => ({
  createDailyIndexForecastModel: createDailyIndexForecastModelMock,
}))

vi.mock('../api/settings', () => ({
  fetchPlatformSettings: fetchPlatformSettingsMock,
  updatePlatformSettings: vi.fn(),
}))

vi.mock('../settings/storage', () => ({
  loadAppearanceSettings: loadAppearanceSettingsMock,
  saveAppearanceSettings: saveAppearanceSettingsMock,
}))

import { DatasetsListPage } from './DatasetsListPage'
import { SettingsProvider } from '../settings/SettingsContext'
import { defaultPlatformSettings } from '../settings/defaults'

describe('DatasetsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    loadAppearanceSettingsMock.mockReturnValue(defaultPlatformSettings.appearance)
    fetchPlatformSettingsMock.mockResolvedValue({
      backtest_defaults: defaultPlatformSettings.backtest_defaults,
      live_defaults: defaultPlatformSettings.live_defaults,
      platform_behavior: defaultPlatformSettings.platform_behavior,
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
          error_message: null,
          progress_pct: 100,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    })
    deleteDatasetMock.mockResolvedValue(undefined)
    createRiskModelMock.mockResolvedValue({ group_id: 'rm-1', status: 'running' })
    createReturnForecastModelMock.mockResolvedValue({ group_id: 'rf-1', status: 'running' })
    createDailyIndexForecastModelMock.mockResolvedValue({ group_id: 'di-1', feature_run_id: 'fr-1', status: 'running' })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows resolution instead of output path in the datasets list', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <SettingsProvider>
          <DatasetsListPage />
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('columnheader', { name: 'Resolution' })).toBeInTheDocument()
    expect(screen.getByText('5m')).toBeInTheDocument()
    expect(screen.queryByText('/tmp/datasets')).not.toBeInTheDocument()

    await waitFor(() =>
      expect(fetchDatasetsMock).toHaveBeenCalled(),
    )
  })

  it('renders dataset status as a colorful pill', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <SettingsProvider>
          <DatasetsListPage />
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Completed').closest('.MuiChip-root')).toBeInTheDocument()
  })

  it('shows a single train model button and can launch a daily index model', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <SettingsProvider>
          <DatasetsListPage />
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: /train model/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /train risk model/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /train return forecast/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getByRole('button', { name: /train model/i }))
    fireEvent.click(screen.getByRole('button', { name: /daily index forecast model/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.queryByLabelText(/start date/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/end date/i)).not.toBeInTheDocument()
    expect(screen.getByText(/uses dataset provenance: aapl from 2026-05-01 to 2026-06-01/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    await waitFor(() =>
      expect(createDailyIndexForecastModelMock).toHaveBeenCalledWith(
        expect.objectContaining({
          universe: expect.objectContaining({
            start_date: '2026-05-01',
            end_date: '2026-06-01',
            symbols: [expect.objectContaining({ symbol: 'AAPL' })],
          }),
        }),
      ),
    )
  })

  it('blocks daily index launches when multiple datasets are selected', async () => {
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
          error_message: null,
          progress_pct: 100,
        },
        {
          id: 'ds-2',
          name: 'Other dataset',
          symbol: 'QQQ',
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
          dataset_parquet_path: '/tmp/datasets/qqq.parquet',
          manifest_path: '/tmp/datasets/qqq.manifest.json',
          error_message: null,
          progress_pct: 100,
        },
      ],
      total: 2,
      page: 1,
      page_size: 2,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <SettingsProvider>
          <DatasetsListPage />
        </SettingsProvider>
      </MemoryRouter>,
    )

    await screen.findByRole('button', { name: /train model/i })
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getAllByRole('checkbox')[2])
    fireEvent.click(screen.getByRole('button', { name: /train model/i }))
    fireEvent.click(screen.getByRole('button', { name: /daily index forecast model/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(await screen.findByText(/requires exactly one dataset selection/i)).toBeInTheDocument()
    expect(createDailyIndexForecastModelMock).not.toHaveBeenCalled()
  })
})
