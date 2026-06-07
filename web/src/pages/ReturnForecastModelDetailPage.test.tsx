import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { defaultPlatformSettings } from '../settings/defaults'

const fetchReturnForecastModelDetailMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelStatusMock = vi.hoisted(() => vi.fn())
const fetchWorkflowMock = vi.hoisted(() => vi.fn())
const fetchWorkflowDebugConfigMock = vi.hoisted(() => vi.fn())
const fetchWorkflowPodLogsMock = vi.hoisted(() => vi.fn())
const fetchReturnForecastModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const deleteReturnForecastModelMock = vi.hoisted(() => vi.fn())
const updateReturnForecastModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/returnForecastModels', () => ({
  fetchReturnForecastModelDetail: fetchReturnForecastModelDetailMock,
  fetchReturnForecastModelStatus: fetchReturnForecastModelStatusMock,
  fetchReturnForecastModelWorkflowErrors: fetchReturnForecastModelWorkflowErrorsMock,
  deleteReturnForecastModel: deleteReturnForecastModelMock,
  updateReturnForecastModel: updateReturnForecastModelMock,
}))

vi.mock('../api/argo', () => ({
  fetchWorkflow: fetchWorkflowMock,
  fetchWorkflowDebugConfig: fetchWorkflowDebugConfigMock,
  fetchWorkflowPodLogs: fetchWorkflowPodLogsMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      ...defaultPlatformSettings,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { ReturnForecastModelDetailPage } from './ReturnForecastModelDetailPage'

describe('ReturnForecastModelDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the training set, targets, metrics, and relevant info sections', async () => {
    fetchReturnForecastModelDetailMock.mockResolvedValue({
      group_id: 'rf-1',
      name: 'Short Horizon Forecast',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {
        backtest_ids: ['b1'],
        train_config: { random_seed: 7 },
      },
      artifact_dir: '/tmp/return-forecast-models/rf-1',
      training_start_date: '2024-01-01',
      training_end_date: '2024-01-10',
      summary_metrics: {
        forecast: { mae: 0.34, rmse: 0.5 },
      },
      dataset_manifest: {
        generated_at: '2026-06-01T12:02:00.000Z',
        dataset_version: 'return_forecast_dataset_v1',
        label_version: 'labels_v1',
        feature_version: 'features_v1',
        config_hash: 'abc123def4567890',
        source_report_paths: ['/tmp/report-a.json'],
        total_candidates: 18,
        labeled_rows: 16,
        feature_rows: 17,
        joined_rows: 15,
        dropped_label_rows: 2,
        dropped_feature_rows: 1,
        duplicate_candidate_ids: 3,
        output_path: '/tmp/return-forecast-models/rf-1/dataset/dataset.parquet',
      },
      sources: [
        {
          backtest_id: 'b1',
          source_report_path: '/tmp/report-a.json',
          created_at: '2026-06-01T11:59:00.000Z',
        },
      ],
      targets: [
        {
          id: 1,
          group_id: 'rf-1',
          target_key: 'forecast_return',
          task_type: 'regression',
          status: 'succeeded',
          model_artifact_path: '/tmp/return-forecast-models/rf-1/targets/forecast_return/model.json',
          metrics: {
            mae: 0.34,
            rmse: 0.5,
            fold_metrics: [
              {
                fold_id: 1,
                train_start: '2024-01-01',
                train_end: '2024-01-03',
                validation_start: '2024-01-03',
                validation_end: '2024-01-04',
                test_start: '2024-01-04',
                test_end: '2024-01-05',
                n_train: 12,
                n_validation: 4,
                n_test: 4,
                validation: { mae: 0.32, rmse: 0.48 },
                test: { mae: 0.35, rmse: 0.52 },
              },
            ],
          },
          dataset_manifest_path: '/tmp/return-forecast-models/rf-1/dataset/manifest.json',
          feature_columns: ['alpha.mean', 'alpha.std', 'beta.value', 'plain_feature', 'plain_other', 'gamma.level'],
          feature_importance: {
            target_key: 'forecast_return',
            rows: [
              { feature: 'alpha.mean', importance: 0.5, signed_importance: 0.25 },
              { feature: 'beta.value', importance: 0.3, signed_importance: -0.12 },
              { feature: 'plain_feature', importance: 0.2, signed_importance: 0.07 },
            ],
          },
          created_at: '2026-06-01T12:00:10.000Z',
          updated_at: '2026-06-01T12:01:10.000Z',
        },
      ],
      feature_importance: {
        target_key: 'forecast_return',
        rows: [
          { feature: 'alpha.mean', importance: 0.5, signed_importance: 0.25 },
          { feature: 'beta.value', importance: 0.3, signed_importance: -0.12 },
          { feature: 'plain_feature', importance: 0.2, signed_importance: 0.07 },
        ],
      },
    })
    fetchReturnForecastModelStatusMock.mockResolvedValue({
      group_id: 'rf-1',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
    })

    render(
      <MemoryRouter initialEntries={['/models/returns/rf-1']}>
        <Routes>
          <Route path="/models/returns/:groupId" element={<ReturnForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Short Horizon Forecast' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Training' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Targets' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Performance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Feature Importance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Debug' })).toBeInTheDocument()
    expect(screen.getAllByText('Error metrics').length).toBeGreaterThan(0)
    expect(screen.getByText('How far predictions miss the realized target values on average.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Targets' }))
    expect(await screen.findByText('Feature browser')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Groups' }))
    expect(screen.getByText('alpha.mean, alpha.std')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Feature Importance' }))
    expect(await screen.findByText('Feature importance')).toBeInTheDocument()
    expect(screen.getByText('alpha.mean')).toBeInTheDocument()
    expect(screen.getByText('50.0%')).toBeInTheDocument()
  })

  it('renames an existing model from the detail page', async () => {
    fetchReturnForecastModelDetailMock.mockResolvedValue({
      group_id: 'rf-rename',
      name: 'Old Return Name',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/return-forecast-models/rf-rename',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })
    fetchReturnForecastModelStatusMock.mockResolvedValue({
      group_id: 'rf-rename',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
    })
    updateReturnForecastModelMock.mockResolvedValue({
      group_id: 'rf-rename',
      name: 'Renamed Return Forecast',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:10:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/return-forecast-models/rf-rename',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })

    render(
      <MemoryRouter initialEntries={['/models/returns/rf-rename']}>
        <Routes>
          <Route path="/models/returns/:groupId" element={<ReturnForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Old Return Name' })).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Rename' }).at(-1)!)
    const nameField = await screen.findByLabelText('Name')
    fireEvent.change(nameField, { target: { value: 'Renamed Return Forecast' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateReturnForecastModelMock).toHaveBeenCalledWith('rf-rename', { name: 'Renamed Return Forecast' }),
    )
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Renamed Return Forecast' })).toBeInTheDocument(),
    )
  })

  it('opens workflow steps and workflow errors', async () => {
    fetchReturnForecastModelDetailMock.mockResolvedValue({
      group_id: 'rf-2',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/return-forecast-models/rf-2',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })
    fetchReturnForecastModelStatusMock.mockResolvedValue({
      group_id: 'rf-2',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
    })
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf', namespace: 'ns' },
      status: {
        phase: 'Failed',
        nodes: {
          step1: {
            id: 'step1',
            name: 'step1',
            displayName: 'Train forecast',
            phase: 'Failed',
            templateName: 'train-forecast',
            podName: 'pod-1',
            inputs: {
              parameters: [{ name: 'dataset', value: 'train.parquet' }],
            },
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.train_forecast' }],
            },
          },
        },
      },
    })
    fetchWorkflowPodLogsMock.mockResolvedValue({
      workflow_name: 'wf',
      namespace: 'ns',
      pod_name: 'pod-1',
      container_name: 'main',
      logs: 'workflow log line',
    })
    fetchWorkflowDebugConfigMock.mockResolvedValue({
      workflow_name: 'wf',
      namespace: 'ns',
      pod_name: 'pod-1',
      terminal_command: 'python -m app.standalone.train_forecast',
      launch_configuration: { type: 'debugpy' },
      snippet: '{"type":"debugpy"}',
    })
    fetchReturnForecastModelWorkflowErrorsMock.mockResolvedValue({
      group_id: 'rf-2',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
      available: true,
      status_message: 'Workflow terminated after a step failure',
      failed_node_name: 'step-1',
      failed_template_name: 'train-forecast',
      error_exception: 'ValueError: boom',
      error_code_location: '/src/app/train.py:42',
      error_call_stack: ['/src/app/train.py:42', '/src/app/main.py:10'],
      error_traceback: 'Traceback (most recent call last):\nValueError: boom',
    })

    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    })

    render(
      <MemoryRouter initialEntries={['/models/returns/rf-2']}>
        <Routes>
          <Route path="/models/returns/:groupId" element={<ReturnForecastModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText(/Return forecast model rf-2/i)).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: /view workflow steps/i })[0])
    await waitFor(() => expect(screen.getByText('Workflow steps')).toBeInTheDocument())
    await waitFor(() => expect(fetchWorkflowPodLogsMock).toHaveBeenCalledWith('wf', 'pod-1', 'ns'))
    fireEvent.click(screen.getByRole('tab', { name: /logs/i }))
    expect(screen.getAllByText('Train forecast').length).toBeGreaterThan(0)
    await screen.findByText(/workflow log line/i)

    fireEvent.click(screen.getByRole('button', { name: /close workflow steps dialog/i }))
    await waitFor(() => expect(screen.queryByText('Workflow steps')).not.toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: /view workflow errors/i })[0])
    expect(await screen.findByText('Workflow errors')).toBeInTheDocument()
    expect(screen.getByText('ValueError: boom at /src/app/train.py:42')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /copy error-exception/i }))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('ValueError: boom')
  })
})
