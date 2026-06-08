import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defaultPlatformSettings } from '../settings/defaults'

const fetchDailyIndexForecastModelDetailMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const deleteDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const retryDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const updateDailyIndexForecastModelMock = vi.hoisted(() => vi.fn())
const fetchDailyIndexForecastModelChartDataMock = vi.hoisted(() => vi.fn())

vi.mock('../api/dailyIndexForecastModels', () => ({
  fetchDailyIndexForecastModelChartData: fetchDailyIndexForecastModelChartDataMock,
  fetchDailyIndexForecastModelDetail: fetchDailyIndexForecastModelDetailMock,
  fetchDailyIndexForecastModelStatus: fetchDailyIndexForecastModelStatusMock,
  fetchDailyIndexForecastModelWorkflowErrors: fetchDailyIndexForecastModelWorkflowErrorsMock,
  deleteDailyIndexForecastModel: deleteDailyIndexForecastModelMock,
  retryDailyIndexForecastModel: retryDailyIndexForecastModelMock,
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
import { chartLoadErrorDetails } from './DailyIndexForecastModelPages'

describe('DailyIndexForecastModelDetailPage charts tab', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()

    const initialDetail = {
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      name: 'Forecast A',
      created_at: '2026-06-05T10:00:00.000Z',
      updated_at: '2026-06-05T10:00:00.000Z',
      status: 'running',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      resolution: '5m',
      params: {},
      artifact_dir: '/tmp/group',
      summary_metrics: null,
      holdout_dates: ['2024-01-03', '2024-01-04', '2024-01-05'],
      feature_run: {
        feature_run_id: 'fr-1',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        resolution: '5m',
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
      feature_importance: null,
      targets: [
        {
          id: 1,
          group_id: 'di-1',
          target_key: 'daily_index_forecast',
          task_type: 'regression',
          status: 'running',
          model_artifact_path: '/tmp/group/model.json',
          metrics: null,
          dataset_manifest_path: null,
          feature_columns: ['open_price', 'rolling_return_20'],
          feature_importance: null,
          created_at: '2026-06-05T10:00:00.000Z',
          updated_at: '2026-06-05T10:00:00.000Z',
        },
      ],
    }

    fetchDailyIndexForecastModelDetailMock.mockResolvedValue(initialDetail)
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
    retryDailyIndexForecastModelMock.mockResolvedValue({
      group_id: 'di-1',
      feature_run_id: 'fr-1',
      status: 'pending',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
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
      split_label: 'holdout',
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
          split_label: 'holdout',
        },
        {
          session_date: '2024-01-03',
          decision_time: '10:30',
          decision_timestamp: '2024-01-03T15:30:00.000Z',
          predicted_bps: -3.4,
          actual_bps: -1.2,
          actual_after_cost: false,
          split_label: 'holdout',
        },
      ],
    })
  })

  it('refreshes the detail payload and renders feature importance after the workflow finishes', async () => {
    fetchDailyIndexForecastModelDetailMock.mockReset()
    fetchDailyIndexForecastModelStatusMock.mockReset()
    fetchDailyIndexForecastModelDetailMock
      .mockResolvedValueOnce({
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        created_at: '2026-06-05T10:00:00.000Z',
        updated_at: '2026-06-05T10:00:00.000Z',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params: {},
        artifact_dir: '/tmp/group',
        summary_metrics: null,
        holdout_dates: ['2024-01-03', '2024-01-04', '2024-01-05'],
        feature_run: {
          feature_run_id: 'fr-1',
          status: 'running',
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
        feature_importance: null,
        targets: [
          {
            id: 1,
            group_id: 'di-1',
            target_key: 'daily_index_forecast',
            task_type: 'regression',
            status: 'running',
            model_artifact_path: '/tmp/group/model.json',
            metrics: null,
            dataset_manifest_path: null,
            feature_columns: ['open_price', 'rolling_return_20'],
            feature_importance: null,
            created_at: '2026-06-05T10:00:00.000Z',
            updated_at: '2026-06-05T10:00:00.000Z',
          },
        ],
      })
      .mockResolvedValueOnce({
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        created_at: '2026-06-05T10:00:00.000Z',
        updated_at: '2026-06-05T10:05:00.000Z',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        resolution: '5m',
        params: {},
        artifact_dir: '/tmp/group',
        summary_metrics: null,
        holdout_dates: ['2024-01-03', '2024-01-04', '2024-01-05'],
        feature_run: {
          feature_run_id: 'fr-1',
          status: 'succeeded',
          argo_namespace: 'ns',
          argo_workflow_name: 'wf',
          symbol: 'SPY',
          benchmark_symbol: 'QQQ',
          resolution: '5m',
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
          updated_at: '2026-06-05T10:05:00.000Z',
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
            updated_at: '2026-06-05T10:05:00.000Z',
          },
        ],
      })
    fetchDailyIndexForecastModelStatusMock
      .mockResolvedValueOnce({
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        argo_phase: 'Running',
        progress_pct: 25,
      })
      .mockResolvedValueOnce({
        group_id: 'di-1',
        feature_run_id: 'fr-1',
        name: 'Forecast A',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        argo_phase: 'Succeeded',
        progress_pct: 100,
      })
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDailyIndexForecastModelDetailMock).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Resolution 5m')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('tab', { name: /feature importance/i })[0])

    expect(await screen.findByText('Feature importance')).toBeInTheDocument()
    expect(await screen.findByText('daily_index_forecast')).toBeInTheDocument()
    expect(screen.getByText('60.0%')).toBeInTheDocument()
  })

  it('deletes a forecast from the detail page', async () => {
    fetchDailyIndexForecastModelDetailMock.mockResolvedValue({
      group_id: 'di-delete',
      feature_run_id: 'fr-delete',
      name: 'Disposable Forecast',
      created_at: '2026-06-05T10:00:00.000Z',
      updated_at: '2026-06-05T10:00:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      resolution: '5m',
      params: {},
      artifact_dir: '/tmp/group',
      summary_metrics: null,
      holdout_dates: [],
      feature_run: null,
      dataset_manifest: null,
      feature_importance: null,
      targets: [],
    })
    fetchDailyIndexForecastModelStatusMock.mockResolvedValue({
      group_id: 'di-delete',
      feature_run_id: 'fr-delete',
      name: 'Disposable Forecast',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
      progress_pct: 100,
    })
    deleteDailyIndexForecastModelMock.mockResolvedValue(undefined)

    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-delete']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Disposable Forecast' })).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1)!)
    expect(
      await screen.findByRole('heading', { name: /delete daily index forecast disposable forecast\?/i }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^delete forecast$/i }))
    await waitFor(() => expect(deleteDailyIndexForecastModelMock).toHaveBeenCalledWith('di-delete'))
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: /delete daily index forecast disposable forecast\?/i }),
      ).not.toBeInTheDocument(),
    )
  })

  it('renders stored chart data for the selected day', async () => {
    fetchDailyIndexForecastModelDetailMock.mockReset()
    fetchDailyIndexForecastModelStatusMock.mockReset()
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
      holdout_dates: ['2024-01-03', '2024-01-04', '2024-01-05'],
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
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDailyIndexForecastModelDetailMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getAllByRole('tab', { name: /charts/i })[0])

    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledTimes(1))
    expect(screen.getAllByText('holdout').length).toBeGreaterThan(0)
    expect(screen.getByText('stored data')).toBeInTheDocument()
    expect(screen.getByTestId('forecast-chart')).toHaveTextContent('09:45 12.3bps')
    expect(screen.getByText('Predictions vs labels')).toBeInTheDocument()
    expect(screen.getByText('+12.3 bps')).toBeInTheDocument()
    expect(screen.getByText('+9.1 bps')).toBeInTheDocument()
    expect(screen.getByText('+3.2 bps')).toBeInTheDocument()
    expect(screen.getByText('After cost: yes')).toBeInTheDocument()
    expect(screen.getByText('-3.4 bps')).toBeInTheDocument()
    expect(screen.getByText('-1.2 bps')).toBeInTheDocument()
    expect(screen.getByText('-2.2 bps')).toBeInTheDocument()
    expect(screen.getByText('After cost: no')).toBeInTheDocument()
  })

  it('caches chart payloads when switching between holdout dates', async () => {
    fetchDailyIndexForecastModelDetailMock.mockReset()
    fetchDailyIndexForecastModelStatusMock.mockReset()
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
      holdout_dates: ['2024-01-03', '2024-01-04'],
      feature_run: {
        feature_run_id: 'fr-1',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-03',
        end_date: '2024-01-04',
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
      feature_importance: null,
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
          feature_importance: null,
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
    fetchDailyIndexForecastModelChartDataMock.mockImplementation(async (_groupId: string, selectedDate: string) => ({
      group_id: 'di-1',
      symbol: 'SPY',
      selected_date: selectedDate,
      resolution: '5m',
      cache_status: 'fresh',
      source: 'stored',
      split_label: 'holdout',
      bars: {
        symbol: 'SPY',
        provider: 'alpaca',
        resolution: '5m',
        start_date: selectedDate,
        stop_date: selectedDate,
        cache_status: 'fresh',
        rows: [
          {
            timestamp: `${selectedDate}T14:30:00.000Z`,
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
          session_date: selectedDate,
          decision_time: '09:45',
          decision_timestamp: `${selectedDate}T14:45:00.000Z`,
          predicted_bps: 12.3,
          actual_bps: 9.1,
          actual_after_cost: true,
          split_label: 'holdout',
        },
      ],
    }))

    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledTimes(0))
    fireEvent.click(screen.getAllByRole('tab', { name: /charts/i })[0])

    const select = await screen.findByRole('combobox', { name: /holdout date/i })
    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(select).toHaveTextContent('Jan 3, 2024'))

    fireEvent.mouseDown(select)
    fireEvent.click(await screen.findByRole('option', { name: 'Jan 4, 2024' }))
    await waitFor(() => expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledTimes(2))

    fireEvent.mouseDown(select)
    fireEvent.click(await screen.findByRole('option', { name: 'Jan 3, 2024' }))
    await waitFor(() => expect(select).toHaveTextContent('Jan 3, 2024'))
    expect(fetchDailyIndexForecastModelChartDataMock).toHaveBeenCalledTimes(2)
  })

  it('limits the chart selector to holdout dates only', async () => {
    fetchDailyIndexForecastModelDetailMock.mockReset()
    fetchDailyIndexForecastModelStatusMock.mockReset()
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
      holdout_dates: ['2024-01-04', '2024-01-05'],
      feature_run: {
        feature_run_id: 'fr-1',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        symbol: 'SPY',
        benchmark_symbol: 'QQQ',
        decision_times: ['09:45'],
        start_date: '2024-01-03',
        end_date: '2024-01-05',
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
      feature_importance: null,
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
          feature_importance: null,
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
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDailyIndexForecastModelDetailMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getAllByRole('tab', { name: /charts/i })[0])

    const select = await screen.findByRole('combobox', { name: /holdout date/i })
    await waitFor(() => expect(select).toHaveTextContent('Jan 4, 2024'))
    await screen.findByTestId('forecast-chart')
    fireEvent.mouseDown(select)
    expect(await screen.findByRole('option', { name: 'Jan 4, 2024' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Jan 5, 2024' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Jan 3, 2024' })).not.toBeInTheDocument()
  })

  it('shows an empty state when no holdout dates are available', async () => {
    fetchDailyIndexForecastModelDetailMock.mockReset()
    fetchDailyIndexForecastModelStatusMock.mockReset()
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
      holdout_dates: [],
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
      feature_importance: null,
      targets: [],
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
    render(
      <MemoryRouter initialEntries={['/models/daily-index/di-1']}>
        <Routes>
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDailyIndexForecastModelDetailMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getAllByRole('tab', { name: /charts/i })[0])

    expect(
      await screen.findByText('This forecast does not have holdout chart dates available yet.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('forecast-chart')).not.toBeInTheDocument()
    expect(fetchDailyIndexForecastModelChartDataMock).not.toHaveBeenCalled()
  })

  it('maps insufficient-history chart errors to the friendly copy', () => {
    expect(chartLoadErrorDetails('Not enough sessions for walk-forward folds')).toEqual({
      severity: 'info',
      message:
        'This model does not have enough session history yet to build walk-forward chart data. Try an earlier date or train with a wider date range.',
    })
  })
})
