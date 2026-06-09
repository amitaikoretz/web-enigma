import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchDatasetDetailMock = vi.hoisted(() => vi.fn())
const fetchDatasetStatusMock = vi.hoisted(() => vi.fn())
const fetchDatasetWorkflowErrorsMock = vi.hoisted(() => vi.fn())
const fetchWorkflowMock = vi.hoisted(() => vi.fn())
const fetchWorkflowDebugConfigMock = vi.hoisted(() => vi.fn())
const fetchWorkflowPodLogsMock = vi.hoisted(() => vi.fn())
const deleteDatasetMock = vi.hoisted(() => vi.fn())
const downloadDatasetParquetMock = vi.hoisted(() => vi.fn())
const retryDatasetMock = vi.hoisted(() => vi.fn())
const fetchPlatformSettingsMock = vi.hoisted(() => vi.fn())
const loadAppearanceSettingsMock = vi.hoisted(() => vi.fn())
const saveAppearanceSettingsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  deleteDataset: deleteDatasetMock,
  downloadDatasetParquet: downloadDatasetParquetMock,
  fetchDatasetDetail: fetchDatasetDetailMock,
  fetchDatasetStatus: fetchDatasetStatusMock,
  fetchDatasetWorkflowErrors: fetchDatasetWorkflowErrorsMock,
  retryDataset: retryDatasetMock,
}))

vi.mock('../api/argo', () => ({
  fetchWorkflow: fetchWorkflowMock,
  fetchWorkflowDebugConfig: fetchWorkflowDebugConfigMock,
  fetchWorkflowPodLogs: fetchWorkflowPodLogsMock,
}))

vi.mock('../api/settings', () => ({
  fetchPlatformSettings: fetchPlatformSettingsMock,
  updatePlatformSettings: vi.fn(),
}))

vi.mock('../settings/storage', () => ({
  loadAppearanceSettings: loadAppearanceSettingsMock,
  saveAppearanceSettings: saveAppearanceSettingsMock,
}))

import { DatasetDetailPage } from './DatasetDetailPage'
import { SettingsProvider } from '../settings/SettingsContext'
import { defaultPlatformSettings } from '../settings/defaults'
import { buildDatasetCopySnippet } from '../utils/datasetCopy'

describe('DatasetDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    loadAppearanceSettingsMock.mockReturnValue(defaultPlatformSettings.appearance)
    fetchPlatformSettingsMock.mockResolvedValue({
      backtest_defaults: defaultPlatformSettings.backtest_defaults,
      live_defaults: defaultPlatformSettings.live_defaults,
      platform_behavior: defaultPlatformSettings.platform_behavior,
    })
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-1',
        name: 'My dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
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
        options_parquet_path: '/tmp/datasets/aapl-options.parquet',
        options_manifest_path: '/tmp/datasets/aapl-options.manifest.json',
        error_message: null,
        progress_pct: 100,
      },
    })
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-1',
      name: 'My dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
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
      options_parquet_path: '/tmp/datasets/aapl-options.parquet',
      options_manifest_path: '/tmp/datasets/aapl-options.manifest.json',
      error_message: null,
      progress_pct: 100,
      is_terminal: true,
    })
    fetchDatasetWorkflowErrorsMock.mockResolvedValue({
      dataset_id: 'ds-1',
      argo_namespace: null,
      argo_workflow_name: null,
      argo_phase: null,
      available: true,
      status_message: 'Loaded error details from the failed workflow step.',
      failed_node_name: 'main',
      failed_template_name: 'main',
      error_exception: 'RuntimeError: boom',
      error_code_location: '/tmp/train.py:42',
      error_call_stack: ['/tmp/train.py:42', '/tmp/train.py:13'],
      error_traceback: 'Traceback (most recent call last):\nboom',
    })
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf', namespace: 'ns' },
      status: {
        phase: 'Failed',
        nodes: {
          node1: {
            id: 'node1',
            name: 'node1',
            displayName: 'main',
            phase: 'Failed',
            templateName: 'main',
            podName: 'pod-1',
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.datasets_download_argo' }],
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
      logs: 'workflow step logs',
    })
    fetchWorkflowDebugConfigMock.mockResolvedValue({
      workflow_name: 'wf',
      namespace: 'ns',
      pod_name: 'pod-1',
      terminal_command: 'python -m app.standalone.datasets_download_argo',
      launch_configuration: {},
      snippet: '{}',
    })
    retryDatasetMock.mockResolvedValue({
      dataset_id: 'ds-1',
      status: 'pending',
      status_url: '/datasets/ds-1/status',
      detail_url: '/datasets/ds-1',
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the dataset title, id, and download action', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'My dataset' })).toBeInTheDocument()
    expect(screen.getByText('ID: ds-1')).toBeInTheDocument()
    expect(screen.getByText('Resolution')).toBeInTheDocument()
    expect(screen.getByText('1d')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /download parquet/i })[0])

    await waitFor(() =>
      expect(downloadDatasetParquetMock).toHaveBeenCalledWith('ds-1'),
    )
  })

  it('copies a Python snippet that loads the dataset artifact', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    const copyButton = await screen.findByRole('button', { name: /copy code/i })
    fireEvent.click(copyButton)

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      buildDatasetCopySnippet({
        manifestPath: '/tmp/datasets/aapl.manifest.json',
        datasetParquetPath: '/tmp/datasets/aapl.parquet',
      }),
    )
    expect(await screen.findByRole('button', { name: /copied/i })).toBeInTheDocument()
  })

  it('shows a single train model button with family choices in a menu', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    const trainButtons = await screen.findAllByRole('button', { name: /train model/i })
    expect(trainButtons).toHaveLength(1)

    fireEvent.click(trainButtons[0])

    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Risk model' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Return forecast model' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Daily index forecast model' })).toBeInTheDocument()
  })

  it('polls dataset status until it fails and shows a determinate progress bar', async () => {
    fetchPlatformSettingsMock.mockResolvedValueOnce({
      backtest_defaults: defaultPlatformSettings.backtest_defaults,
      live_defaults: defaultPlatformSettings.live_defaults,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        auto_refresh_interval_seconds: 1,
      },
    })

    fetchDatasetDetailMock
      .mockResolvedValueOnce({
        metadata: {
          id: 'ds-5',
          name: 'Running dataset',
          symbol: 'AAPL',
          provider: 'alpaca',
          resolution: '1d',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'running',
          argo_namespace: 'ns',
          argo_workflow_name: 'wf',
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: null,
          manifest_path: null,
          options_parquet_path: null,
          options_manifest_path: null,
          error_message: null,
          progress_pct: 37,
        },
      })
      .mockResolvedValueOnce({
        metadata: {
          id: 'ds-5',
          name: 'Running dataset',
          symbol: 'AAPL',
          provider: 'alpaca',
          resolution: '1d',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'failed',
          argo_namespace: 'ns',
          argo_workflow_name: 'wf',
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: null,
          manifest_path: null,
          options_parquet_path: null,
          options_manifest_path: null,
          error_message: 'boom',
          progress_pct: 100,
        },
      })
    fetchDatasetStatusMock
      .mockResolvedValueOnce({
        id: 'ds-5',
        name: 'Running dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'running',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: null,
        progress_pct: 37,
        is_terminal: false,
      })
      .mockResolvedValueOnce({
        id: 'ds-5',
        name: 'Running dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: 'boom',
        progress_pct: 100,
        is_terminal: true,
      })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-5']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Running dataset')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /edit and resubmit/i })).toBeInTheDocument()

    await waitFor(() => expect(fetchDatasetStatusMock).toHaveBeenCalledTimes(2))

    expect(await screen.findByText('Failed')).toBeInTheDocument()
    expect(await screen.findByText('100.0% complete')).toBeInTheDocument()
  })

  it('links edit and resubmit into the dataset wizard', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: /edit and resubmit/i })).toBeEnabled()
  })

  it('merges live status artifact paths into the detail view', async () => {
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-4',
        name: 'Merged dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'completed',
        argo_namespace: null,
        argo_workflow_name: null,
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: null,
        progress_pct: 100,
      },
    })
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-4',
      name: 'Merged dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
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
      options_parquet_path: '/tmp/datasets/aapl-options.parquet',
      options_manifest_path: '/tmp/datasets/aapl-options.manifest.json',
      error_message: null,
      progress_pct: 100,
      is_terminal: true,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-4']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Artifact outputs')).toBeInTheDocument()
    expect(screen.getByText('/tmp/datasets/aapl.parquet')).toBeInTheDocument()
    expect(screen.getByText('/tmp/datasets/aapl.manifest.json')).toBeInTheDocument()
    expect(screen.getByText('/tmp/datasets/aapl-options.parquet')).toBeInTheDocument()
    expect(screen.getByText('/tmp/datasets/aapl-options.manifest.json')).toBeInTheDocument()
  })

  it('allows download even when the parquet path is not stored explicitly', async () => {
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-2',
        name: 'Fallback dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'completed',
        argo_namespace: null,
        argo_workflow_name: null,
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: null,
        progress_pct: 100,
      },
    })
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-2',
      name: 'Fallback dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
      start_date: '2026-05-01',
      end_date: '2026-06-01',
      created_at: '2026-06-07T00:00:00Z',
      updated_at: '2026-06-07T00:00:00Z',
      status: 'completed',
      argo_namespace: null,
      argo_workflow_name: null,
      params_json: {},
      output_dir: '/tmp/datasets',
      dataset_parquet_path: null,
      manifest_path: null,
      options_parquet_path: null,
      options_manifest_path: null,
      error_message: null,
      progress_pct: 100,
      is_terminal: true,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-2']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    const downloadButtons = await screen.findAllByRole('button', { name: /download parquet/i })
    expect(downloadButtons[0]).toBeEnabled()
    fireEvent.click(downloadButtons[0])

    await waitFor(() =>
      expect(downloadDatasetParquetMock).toHaveBeenCalledWith('ds-2'),
    )
  })

  it('shows a retry button for failed datasets and launches a retry through the confirmation modal', async () => {
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-3',
        name: 'Failed dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        params_json: {},
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: 'boom',
        progress_pct: 100,
      },
    })
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-3',
      name: 'Failed dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
      start_date: '2026-05-01',
      end_date: '2026-06-01',
      created_at: '2026-06-07T00:00:00Z',
      updated_at: '2026-06-07T00:00:00Z',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      params_json: {},
      output_dir: '/tmp/datasets',
      dataset_parquet_path: null,
      manifest_path: null,
      options_parquet_path: null,
      options_manifest_path: null,
      error_message: 'boom',
      progress_pct: 100,
      is_terminal: true,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-3']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    const retryButton = await screen.findByRole('button', { name: /retry dataset/i })
    expect(retryButton).toBeEnabled()

    fireEvent.click(retryButton)

    expect(await screen.findByText('Retry dataset?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^retry dataset$/i }))

    await waitFor(() => expect(retryDatasetMock).toHaveBeenCalledWith('ds-3'))
    expect(await screen.findByText('Dataset retry submitted')).toBeInTheDocument()
    expect(screen.getByText('Dataset retry submitted successfully.')).toBeInTheDocument()
  })

  it('opens workflow errors from the detail page', async () => {
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-1',
      name: 'My dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
      start_date: '2026-05-01',
      end_date: '2026-06-01',
      created_at: '2026-06-07T00:00:00Z',
      updated_at: '2026-06-07T00:00:00Z',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      output_dir: '/tmp/datasets',
      dataset_parquet_path: null,
      manifest_path: null,
      options_parquet_path: null,
      options_manifest_path: null,
      error_message: 'boom',
      progress_pct: 100,
      is_terminal: true,
    })
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-1',
        name: 'My dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: 'boom',
        progress_pct: 100,
      },
    })
    fetchDatasetWorkflowErrorsMock.mockResolvedValue({
      dataset_id: 'ds-1',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      argo_phase: 'Failed',
      available: true,
      status_message: 'Loaded error details from the failed workflow step.',
      failed_node_name: 'main',
      failed_template_name: 'main',
      error_exception: 'RuntimeError: boom',
      error_code_location: '/tmp/train.py:42',
      error_call_stack: ['/tmp/train.py:42', '/tmp/train.py:13'],
      error_traceback: 'Traceback (most recent call last):\nboom',
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /view workflow errors/i }))
    expect(await screen.findByText('RuntimeError: boom')).toBeInTheDocument()
  })

  it('opens the workflow steps dialog from the detail page', async () => {
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'ds-1',
        name: 'My dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-05-01',
        end_date: '2026-06-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'failed',
        argo_namespace: 'ns',
        argo_workflow_name: 'wf',
        output_dir: '/tmp/datasets',
        dataset_parquet_path: null,
        manifest_path: null,
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: 'boom',
        progress_pct: 100,
      },
    })
    fetchDatasetStatusMock.mockResolvedValue({
      id: 'ds-1',
      name: 'My dataset',
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
      start_date: '2026-05-01',
      end_date: '2026-06-01',
      created_at: '2026-06-07T00:00:00Z',
      updated_at: '2026-06-07T00:00:00Z',
      status: 'failed',
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
      output_dir: '/tmp/datasets',
      dataset_parquet_path: null,
      manifest_path: null,
      options_parquet_path: null,
      options_manifest_path: null,
      error_message: 'boom',
      progress_pct: 100,
      is_terminal: true,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/ds-1']}>
        <SettingsProvider>
          <Routes>
            <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /view workflow steps/i }))
    expect(await screen.findByRole('dialog', { name: /workflow steps/i })).toBeInTheDocument()
    expect(await screen.findByText(/My dataset.*wf/i)).toBeInTheDocument()
  })
})
