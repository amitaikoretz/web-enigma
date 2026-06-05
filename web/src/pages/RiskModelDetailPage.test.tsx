import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchRiskModelDetailMock = vi.hoisted(() => vi.fn())
const fetchRiskModelStatusMock = vi.hoisted(() => vi.fn())
const fetchWorkflowMock = vi.hoisted(() => vi.fn())
const fetchWorkflowDebugConfigMock = vi.hoisted(() => vi.fn())
const fetchWorkflowPodLogsMock = vi.hoisted(() => vi.fn())
const fetchRiskModelWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const updateRiskModelMock = vi.hoisted(() => vi.fn())

vi.mock('../api/riskModels', () => ({
  fetchRiskModelDetail: fetchRiskModelDetailMock,
  fetchRiskModelStatus: fetchRiskModelStatusMock,
  fetchRiskModelWorkflowErrors: fetchRiskModelWorkflowErrorsMock,
  updateRiskModel: updateRiskModelMock,
}))

vi.mock('../api/argo', () => ({
  fetchWorkflow: fetchWorkflowMock,
  fetchWorkflowDebugConfig: fetchWorkflowDebugConfigMock,
  fetchWorkflowPodLogs: fetchWorkflowPodLogsMock,
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

import { RiskModelDetailPage } from './RiskModelDetailPage'

describe('RiskModelDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the training set, targets, metrics, and relevant info sections', async () => {
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-1',
      name: 'Momentum Risk V1',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {
        backtest_ids: ['b1'],
        train_config: { random_seed: 7 },
      },
      artifact_dir: '/tmp/risk-models/g-1',
      training_start_date: '2024-01-01',
      training_end_date: '2024-01-10',
      summary_metrics: {
        stop_prob: { auc_calibrated: 0.77, brier_calibrated: 0.12 },
        mae: { mae: 0.34, rmse: 0.5 },
      },
      dataset_manifest: {
        generated_at: '2026-06-01T12:02:00.000Z',
        dataset_version: 'risk_dataset_v1',
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
        output_path: '/tmp/risk-models/g-1/dataset/dataset.parquet',
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
          group_id: 'g-1',
          target_key: 'stop_prob',
          task_type: 'classification',
          status: 'succeeded',
          model_artifact_path: '/tmp/risk-models/g-1/targets/stop_prob/model.json',
          metrics: {
            auc_calibrated: 0.77,
            brier_calibrated: 0.12,
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
                validation: { auc_calibrated: 0.75, brier_calibrated: 0.11 },
                test: { auc_calibrated: 0.73, brier_calibrated: 0.13 },
              },
            ],
          },
          dataset_manifest_path: '/tmp/risk-models/g-1/dataset/manifest.json',
          feature_columns: ['alpha.mean', 'alpha.std', 'beta.value', 'plain_feature', 'plain_other', 'gamma.level'],
          created_at: '2026-06-01T12:00:10.000Z',
          updated_at: '2026-06-01T12:01:10.000Z',
        },
      ],
    })
    fetchRiskModelStatusMock.mockResolvedValue({
      group_id: 'g-1',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
    })

    render(
      <MemoryRouter initialEntries={['/models/risk/g-1']}>
        <Routes>
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Momentum Risk V1' })).toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Training' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Targets' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Performance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Debug' })).toBeInTheDocument()
    expect(screen.getByText('Training snapshot')).toBeInTheDocument()
    expect(screen.getByText('Headline metrics')).toBeInTheDocument()
    expect(screen.getAllByText('Calibration metrics').length).toBeGreaterThan(0)
    expect(screen.getByText('How well predicted probabilities line up with the observed outcomes.')).toBeInTheDocument()
    expect(screen.getAllByText('Error metrics').length).toBeGreaterThan(0)
    expect(screen.getByText('Status panel')).toBeInTheDocument()
    expect(screen.getByText('Quick facts')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Targets' }))
    expect(await screen.findByText('Feature browser')).toBeInTheDocument()
    expect(screen.getByText('Feature preview')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Groups' }))
    expect(screen.getByText('alpha.mean, alpha.std')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    expect(screen.getAllByText('plain_feature').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: 'Training' }))
    expect(screen.getByText('Source backtests')).toBeInTheDocument()
    expect(screen.getByText('Dataset manifest summary')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Targets' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Fold metrics (1)' }))
    expect(await screen.findAllByText('Fold 1')).toHaveLength(2)
    expect(screen.getAllByText('Calibration metrics').length).toBeGreaterThan(0)
    expect(screen.getByText('Fold comparison')).toBeInTheDocument()
    expect(screen.getAllByText('Validation').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Test').length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('tab', { name: 'Summary' }).at(-1)!)
    expect(screen.getByText('auc_calibrated')).toBeInTheDocument()
    expect(screen.queryByText('Fold 1')).not.toBeInTheDocument()
  })

  it('renames an existing model from the detail page', async () => {
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-rename',
      name: 'Original Name',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/risk-models/g-rename',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })
    fetchRiskModelStatusMock.mockResolvedValue({
      group_id: 'g-rename',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
    })
    updateRiskModelMock.mockResolvedValue({
      group_id: 'g-rename',
      name: 'Renamed Risk Model',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:10:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/risk-models/g-rename',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })

    render(
      <MemoryRouter initialEntries={['/models/risk/g-rename']}>
        <Routes>
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Original Name' })).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Rename' }).at(-1)!)
    const nameField = await screen.findByLabelText('Name')
    fireEvent.change(nameField, { target: { value: 'Renamed Risk Model' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updateRiskModelMock).toHaveBeenCalledWith('g-rename', { name: 'Renamed Risk Model' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Renamed Risk Model' })).toBeInTheDocument())
  })

  it('polls active models until they reach a terminal state', async () => {
    fetchRiskModelDetailMock
      .mockResolvedValueOnce({
        group_id: 'g-1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:01:00.000Z',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params: {},
        artifact_dir: '/tmp/risk-models/g-1',
        summary_metrics: null,
        dataset_manifest: null,
        sources: [],
        targets: [],
      })
      .mockResolvedValueOnce({
        group_id: 'g-1',
        created_at: '2026-06-01T12:00:00.000Z',
        updated_at: '2026-06-01T12:05:00.000Z',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params: {},
        artifact_dir: '/tmp/risk-models/g-1',
        summary_metrics: null,
        dataset_manifest: null,
        sources: [],
        targets: [],
      })

    fetchRiskModelStatusMock
      .mockResolvedValueOnce({
        group_id: 'g-1',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        argo_phase: 'Running',
      })
      .mockResolvedValueOnce({
        group_id: 'g-1',
        status: 'succeeded',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        argo_phase: 'Succeeded',
      })

    render(
      <MemoryRouter initialEntries={['/models/risk/g-1']}>
        <Routes>
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchRiskModelDetailMock.mock.calls.length).toBeGreaterThanOrEqual(2))
    expect(fetchRiskModelStatusMock.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('succeeded').length).toBeGreaterThan(0)
  })

  it('opens the workflow steps modal from the page action', async () => {
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-2',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/risk-models/g-2',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })
    fetchRiskModelStatusMock.mockResolvedValue({
      group_id: 'g-2',
      status: 'succeeded',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Succeeded',
    })
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf', namespace: 'ns' },
      status: {
        phase: 'Succeeded',
        nodes: {
          step1: {
            id: 'step1',
            name: 'step1',
            displayName: 'Train model',
            phase: 'Succeeded',
            templateName: 'train-model',
            podName: 'pod-1',
            inputs: {
              parameters: [{ name: 'dataset', value: 'train.parquet' }],
            },
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.train_model' }],
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
      terminal_command: 'python -m app.standalone.train_model',
      launch_configuration: { type: 'debugpy' },
      snippet: '{"type":"debugpy"}',
    })

    render(
      <MemoryRouter initialEntries={['/models/risk/g-2']}>
        <Routes>
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText(/Risk model g-2/i)).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: /view workflow steps/i })[0])

    await waitFor(() => expect(screen.getByText('Workflow steps')).toBeInTheDocument())
    await waitFor(() => expect(fetchWorkflowPodLogsMock).toHaveBeenCalledWith('wf', 'pod-1', 'ns'))
    fireEvent.click(screen.getByRole('tab', { name: /logs/i }))
    expect(screen.getAllByText('Train model').length).toBeGreaterThan(0)
    await screen.findByText(/workflow log line/i)
  })

  it('opens workflow errors with a readable failure summary', async () => {
    fetchRiskModelDetailMock.mockResolvedValue({
      group_id: 'g-3',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params: {},
      artifact_dir: '/tmp/risk-models/g-3',
      summary_metrics: null,
      dataset_manifest: null,
      sources: [],
      targets: [],
    })
    fetchRiskModelStatusMock.mockResolvedValue({
      group_id: 'g-3',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
    })
    fetchRiskModelWorkflowErrorsMock.mockResolvedValue({
      group_id: 'g-3',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
      available: true,
      status_message: 'Workflow terminated after a step failure',
      failed_node_name: 'step-1',
      failed_template_name: 'train-model',
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
      <MemoryRouter initialEntries={['/models/risk/g-3']}>
        <Routes>
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText(/Risk model g-3/i)).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: /view workflow errors/i })[0])

    expect(await screen.findByText('Workflow errors')).toBeInTheDocument()
    expect(screen.getByText('Failure summary')).toBeInTheDocument()
    expect(screen.getByText('ValueError: boom at /src/app/train.py:42')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /copy error-exception/i }))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('ValueError: boom')
  })
})
