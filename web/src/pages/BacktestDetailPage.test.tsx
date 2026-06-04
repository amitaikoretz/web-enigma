import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchBacktestDetailMock = vi.hoisted(() => vi.fn())
const fetchBacktestStatusMock = vi.hoisted(() => vi.fn())
const fetchWorkflowMock = vi.hoisted(() => vi.fn())
const fetchWorkflowDebugConfigMock = vi.hoisted(() => vi.fn())
const fetchWorkflowPodLogsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  backtestReportUrl: vi.fn(),
  deleteBacktest: vi.fn(),
  fetchBacktestDetail: fetchBacktestDetailMock,
  fetchBacktestStatus: fetchBacktestStatusMock,
  retryBacktest: vi.fn(),
  retryBacktestForce: vi.fn(),
  updateBacktest: vi.fn(),
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

vi.mock('../components/BacktestProgressPanel', () => ({
  BacktestProgressPanel: () => <div data-testid="progress-panel" />,
}))

vi.mock('../components/BacktestStatusChip', () => ({
  BacktestStatusChip: ({ status }: { status: string }) => <div data-testid="backtest-status">{status}</div>,
  ReportStatusChip: ({ status }: { status: string }) => <div data-testid="report-status">{status}</div>,
}))

vi.mock('../components/BacktestArtifactInventory', () => ({
  BacktestArtifactInventory: () => <div data-testid="artifact-inventory" />,
}))

vi.mock('../components/BacktestCliCommandsSection', () => ({
  BacktestCliCommandsSection: () => <div data-testid="cli-commands" />,
}))

vi.mock('../components/BacktestConfigInspector', () => ({
  BacktestConfigInspector: () => <div data-testid="config-inspector" />,
}))

vi.mock('../components/BacktestRunDetailPanel', () => ({
  BacktestRunDetailPanel: () => <div data-testid="run-detail" />,
}))

vi.mock('../components/BacktestRunsComparisonTable', () => ({
  BacktestRunsComparisonTable: () => <div data-testid="runs-table" />,
}))

vi.mock('../components/BacktestStrategyAggregatePanel', () => ({
  BacktestStrategyAggregatePanel: () => <div data-testid="strategy-panel" />,
}))

vi.mock('../components/BacktestSummaryDashboard', () => ({
  BacktestSummaryDashboard: () => <div data-testid="summary-dashboard" />,
}))

import { BacktestDetailPage } from './BacktestDetailPage'

function buildBacktestDetail() {
  return {
    metadata: {
      id: 'bt-1',
      name: 'Demo backtest',
      created_at: '2026-06-01T12:00:00.000Z',
      updated_at: '2026-06-01T12:01:00.000Z',
      status: 'completed',
      report_status: 'success',
      total_runs: 1,
      completed_runs: 1,
      successful_runs: 1,
      failed_runs: 0,
      selection: {
        start_date: '2026-05-01',
        end_date: '2026-05-31',
        resolution: '1d',
        feed: 'iex',
        symbols: ['AAPL'],
        triggers: ['trigger'],
        exit_rules: ['exit'],
      },
      error_message: null,
      execution_backend: 'argo',
      workflow_name: 'wf-1',
      workflow_namespace: 'ns',
      started_at: '2026-06-01T12:00:00.000Z',
      finished_at: '2026-06-01T12:05:00.000Z',
      progress_pct: 100,
      progress_source: 'argo',
    },
    output_path: '/tmp/backtests/bt-1/output',
    report: {
      generated_at: '2026-06-01T12:05:00.000Z',
      app_version: '1.0.0',
      config_sha256: 'abcdef0123456789',
      input_config_path: null,
      input_config: {},
      total_runs: 1,
      successful_runs: 1,
      failed_runs: 0,
      status: 'success',
      results: [
        {
          run_id: 'run-1',
          name: 'run-1',
          status: 'success',
          strategy: 'strategy-1',
          symbol: 'AAPL',
          data_source: 'iex',
          summary: null,
          analyzers: {},
          orders: [],
          trades: [],
          error: null,
        },
      ],
    },
    artifacts: [],
  }
}

describe('BacktestDetailPage', () => {
  it('opens the workflow steps modal from the workflow action', async () => {
    fetchBacktestDetailMock.mockResolvedValue(buildBacktestDetail())
    fetchBacktestStatusMock.mockResolvedValue({
      ...buildBacktestDetail().metadata,
      progress_pct: 100,
      is_terminal: true,
    })
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf-1', namespace: 'ns' },
      status: {
        phase: 'Succeeded',
        nodes: {
          step1: {
            id: 'step1',
            name: 'step1',
            displayName: 'Load universe',
            phase: 'Succeeded',
            templateName: 'load-universe',
            podName: 'pod-1',
            inputs: {
              parameters: [{ name: 'universe', value: 'demo' }],
            },
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.load_universe' }],
            },
          },
        },
      },
    })
    fetchWorkflowPodLogsMock.mockResolvedValue({
      workflow_name: 'wf-1',
      namespace: 'ns',
      pod_name: 'pod-1',
      container_name: 'main',
      logs: 'workflow step logs',
    })
    fetchWorkflowDebugConfigMock.mockResolvedValue({
      workflow_name: 'wf-1',
      namespace: 'ns',
      pod_name: 'pod-1',
      terminal_command: 'python -m app.standalone.load_universe',
      launch_configuration: { type: 'debugpy' },
      snippet: '{"type":"debugpy"}',
    })

    render(
      <MemoryRouter initialEntries={['/backtests/bt-1']}>
        <Routes>
          <Route path="/backtests/:backtestId" element={<BacktestDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Submission summary')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: /view workflow steps/i })[0])

    await waitFor(() => expect(screen.getByText('Workflow steps')).toBeInTheDocument())
    await waitFor(() => expect(fetchWorkflowPodLogsMock).toHaveBeenCalledWith('wf-1', 'pod-1', 'ns'))
    fireEvent.click(screen.getByRole('tab', { name: /logs/i }))
    expect(screen.getAllByText('Load universe').length).toBeGreaterThan(0)
    await screen.findByText(/workflow step logs/i)
  })
})
