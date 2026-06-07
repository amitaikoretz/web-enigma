import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defaultPlatformSettings } from '../settings/defaults'

const fetchDailyIndexForecastModelDetailMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const updateDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelChartDataMock = vi.hoisted(() => vi.fn())

vi.mock('../api/dailyIndexForecastModels', () => ({
  fetchDailyIndexForecastModelChartData: fetchDailyIndexForecastModelChartDataMock,
  fetchDailyIndexForecastModelDetail: fetchDailyIndexForecastModelDetailMock,
  fetchDailyIndexForecastModelStatus: fetchDailyIndexForecastModelStatusMock,
  fetchDailyIndexForecastModelWorkflowErrors: fetchDailyIndexForecastModelWorkflowErrorsMock,
  updateDailyIndexForecastModel: updateDailyIndexForecastModelMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      ...defaultPlatformSettings,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        auto_refresh_interval_seconds: 60,
        timezone: 'America/New_York',
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

vi.mock('../components/CandlestickChart', () => ({
  CandlestickChart: ({ annotationMarkers }: { annotationMarkers?: Array<{ text?: string }> }) => (
    <div data-testid="forecast-chart">{annotationMarkers?.map((marker) => marker.text).join(' | ')}</div>
  ),
}))

import { DailyIndexForecastModelDetailPage } from './DailyIndexForecastModelDetailPage'

describe('DailyIndexForecastModelDetailPage charts tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchDailyIndexForecastModelDetailMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      name: 'Forecast A',
      created_at: '2026-06-05T10:00:00.000Z',
      updated_at: '2026-06-05T10:00:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/group',
      summary_metrics: null,
      feature_run: {
        feature_run_id: 'fr-1',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-03',
        end_date: '2024-01-03',
        params: {},
        artifact_dir: '/tmp/feature',
        manifest: null,
        summary_metrics: null,
        features_parquet_path: null,
        labels_parquet_path: null,
        created_at: '2026-06-05T10:00:00.000Z',
        updated_at: '2026-06-05T10:00:00.000Z',
      },
      dataset_manifest: null,
      feature_importance: {
        target_key: 'daily_index_forecast',
        rows: [
          { feature: 'open_price', importance: 0.6, signed_importance: 0.4 },
          { feature: 'rolling_return_20', importance: 0.4, signed_importance: -0.2 },
        ],
      },
      targets: [
        {
          id: 1,
          group_id: 'di-1',
          target_key: 'daily_index_forecast',
          task_type: 'regression',
          status: 'succeeded',
          model_artifact_path: '/tmp/group/model.json',
          metrics: null,
          dataset_manifest_path: null,
          feature_columns: ['open_price', 'rolling_return_20'],
          feature_importance: {
            target_key: 'daily_index_forecast',
            rows: [
              { feature: 'open_price', importance: 0.6, signed_importance: 0.4 },
              { feature: 'rolling_return_20', importance: 0.4, signed_importance: -0.2 },
            ],
          },
          created_at: '2026-06-05T10:00:00.000Z',
          updated_at: '2026-06-05T10:00:00.000Z',
        },
      ],
    })
    fetchDailyIndexForecastModelStatusMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      name: 'Forecast A',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
      progress_pct: 100,
    })
    fetchDailyIndexForecastModelWorkflowErrorsMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
      available: false,
      error_call_stack: [],
    })
    fetchDailyIndexForecastModelChartDataMock.mockResolvedValue({
      group_id: 'di-1',
      symbol: 'SPY',
      selected_date: '2024-01-03',
      resolution: '5m',
      cache_status: 'fresh',
      source: 'stored',
      split_label: 'validation',
      bars: {
        symbol: 'SPY',
        provider: 'alpaca',
        resolution: '5m',
        start_date: '2024-01-03',
        stop_date: '2024-01-03',
        cache_status: 'fresh',
        rows: [
          {
            timestamp: '2024-01-03T14:30:00.000Z',
            open: 100,
            high: 101,
            low: 99,
            close: 100.5,
            volume: 1000,
          },
        ],
      },
      predictions: [
        {
          session_date: '2024-01-03',
          decision_time: '09:45',
          decision_timestamp: '2024-01-03T14:45:00.000Z',
          predicted_bps: 12.3,
          actual_bps: 9.1,
          actual_after_cost: true,
          split_label: 'validation',
        },
      ],
    })
  })

  it('loads the charts tab and refreshes when the date changes', async () => {
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Forecast A')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('tab', { name: /charts/i }))
    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledWith('di-1', '2024-01-03'))

    expect(screen.getByText('validation')).toBeInTheDocument()
    expect(screen.getByText('stored data')).toBeInTheDocument()
    expect(screen.getByTestId('forecast-chart')).toHaveTextContent('09:45 12.3bps')

    fireEvent.change(screen.getByLabelText(/date/i), { target: { value: '2024-01-04' } })
    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledWith('di-1', '2024-01-04'))
  })

  it('renders the feature importance tab', async () => {
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Forecast A')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('tab', { name: /feature importance/i })[0])
    expect(await screen.findByText('Feature importance')).toBeInTheDocument()
    expect(screen.getByText('daily_index_forecast')).toBeInTheDocument()
    expect(screen.getByText('60.0%')).toBeInTheDocument()
  })
})
