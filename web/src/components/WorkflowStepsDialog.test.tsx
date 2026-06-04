import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const fetchWorkflowMock = vi.hoisted(() => vi.fn())
const fetchWorkflowDebugConfigMock = vi.hoisted(() => vi.fn())
const fetchWorkflowPodLogsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/argo', () => ({
  fetchWorkflow: fetchWorkflowMock,
  fetchWorkflowDebugConfig: fetchWorkflowDebugConfigMock,
  fetchWorkflowPodLogs: fetchWorkflowPodLogsMock,
}))

import { WorkflowStepsDialog } from './WorkflowStepsDialog'

function buildWorkflowResponse() {
  return {
    metadata: { name: 'wf-1', namespace: 'ns' },
    status: {
      phase: 'Running',
      nodes: {
        node1: {
          id: 'node1',
          name: 'node1',
          displayName: 'Load market data',
          phase: 'Succeeded',
          templateName: 'load-data',
          podName: 'pod-1',
          startedAt: '2026-06-04T10:00:00.000Z',
          finishedAt: '2026-06-04T10:00:05.000Z',
          inputs: {
            parameters: [{ name: 'symbol', value: 'AAPL' }],
          },
          outputs: {
            parameters: [
              { name: 'terminal-command', value: 'python -m app.standalone.load_data --symbol AAPL' },
              { name: 'result-path', value: '/tmp/result-a.json' },
            ],
          },
        },
        node2: {
          id: 'node2',
          name: 'backtest-e193fd02fd61-f96c23[2].run-shards(2:config_path:/data/backtest-results/e193fd02fd6145c9a46a1e29d351913e/shards/hon_volume_rally.yaml,output_path:/data/backtest-results/e193fd02fd6145c9a46a1e29d351913e/shards/hon_volume_rally.json,shard_id:hon_volume_rally)',
          displayName: 'run-shards',
          phase: 'Succeeded',
          templateName: 'run-backtest',
          podName: 'backtest-e193fd02fd61-f96c23-abc123',
          startedAt: '2026-06-04T10:00:06.000Z',
          inputs: {
            parameters: [{ name: 'symbol', value: 'MSFT' }],
          },
          outputs: {
            parameters: [
              { name: 'terminal-command', value: 'python -m app.standalone.run_backtest --symbol MSFT' },
              { name: 'error-exception', value: 'RuntimeError: boom' },
            ],
          },
        },
      },
    },
  }
}

describe('WorkflowStepsDialog', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders workflow steps, switches details, and copies the debug snippet', async () => {
    const clipboardWrite = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: clipboardWrite,
      },
    })

    fetchWorkflowMock.mockResolvedValue(buildWorkflowResponse())
    fetchWorkflowPodLogsMock.mockImplementation(async (_workflowName: string, podName: string) => {
      return {
        workflow_name: 'wf-1',
        namespace: 'ns',
        pod_name: podName,
        container_name: 'main',
        logs: podName === 'pod-1' ? 'pod-1 logs\nline two' : 'pod-2 logs',
      }
    })
    fetchWorkflowDebugConfigMock.mockImplementation(async (_workflowName: string, podName: string) => {
      return {
        workflow_name: 'wf-1',
        namespace: 'ns',
        pod_name: podName,
        terminal_command:
          podName === 'pod-1'
            ? 'python -m app.standalone.load_data --symbol AAPL'
            : 'python -m app.standalone.run_backtest --symbol MSFT',
        launch_configuration: {
          type: 'debugpy',
          request: 'launch',
          module: podName === 'pod-1' ? 'app.standalone.load_data' : 'app.standalone.run_backtest',
          args: podName === 'pod-1' ? ['--symbol', 'AAPL'] : ['--symbol', 'MSFT'],
          env: {
            PYTHONPATH: '${workspaceFolder}/src',
          },
        },
        snippet: JSON.stringify({ podName }, null, 2),
      }
    })

    render(
      <WorkflowStepsDialog
        open
        onClose={() => undefined}
        entityKind="Backtest"
        entityLabel="Backtest demo-1"
        workflowName="wf-1"
        namespace="ns"
        workflowTitle="Demo workflow"
      />,
    )

    await waitFor(() => expect(fetchWorkflowPodLogsMock).toHaveBeenCalledWith('wf-1', 'pod-1', 'ns'))
    fireEvent.click(screen.getByRole('tab', { name: /inputs/i }))
    await screen.findByText('AAPL')

    fireEvent.click(screen.getByRole('tab', { name: /outputs/i }))
    expect(screen.getByText('result-path')).toBeInTheDocument()

    await screen.findByRole('tab', { name: /logs/i })
    fireEvent.click(screen.getByRole('tab', { name: /logs/i }))
    await screen.findByText(/pod-1 logs/)

    fireEvent.click(screen.getByRole('button', { name: /debug/i }))
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalled())
    expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('"podName": "pod-1"'))

    const noisyStepCard = screen.getByText('run-shards').closest('button') ?? screen.getByText('run-shards').closest('[role="button"]')
    expect(within(noisyStepCard as HTMLElement).getByText('backtest-e193fd02fd61-f96c23-abc123')).toBeInTheDocument()

    fireEvent.click(noisyStepCard as HTMLElement)
    await waitFor(() => expect(fetchWorkflowPodLogsMock).toHaveBeenCalledWith('wf-1', 'backtest-e193fd02fd61-f96c23-abc123', 'ns'))
    fireEvent.click(screen.getByRole('tab', { name: /inputs/i }))
    await screen.findByText('MSFT')
    fireEvent.click(screen.getByRole('tab', { name: /outputs/i }))
    expect(screen.getByText('RuntimeError: boom')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /logs/i }))
    await screen.findByText(/pod-2 logs/)
  })

  it('shows an empty state when the workflow only contains nodes without a pod identifier', async () => {
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf-2', namespace: 'ns' },
      status: {
        phase: 'Succeeded',
        nodes: {
          node1: {
            id: 'node1',
            name: 'print-payload',
            displayName: 'print-payload',
            phase: 'Succeeded',
            templateName: 'print-payload',
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.print_argo_payload' }],
            },
          },
        },
      },
    })

    render(
      <WorkflowStepsDialog
        open
        onClose={() => undefined}
        entityKind="Backtest"
        entityLabel="Backtest no-pod"
        workflowName="wf-2"
        namespace="ns"
      />,
    )

    expect(fetchWorkflowPodLogsMock).not.toHaveBeenCalled()
    expect(fetchWorkflowDebugConfigMock).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('No workflow steps were returned for this workflow.'),
    )
  })

  it('shows an error state when the workflow cannot be loaded', async () => {
    fetchWorkflowMock.mockRejectedValueOnce(new Error('Failed to load workflow'))

    render(
      <WorkflowStepsDialog
        open
        onClose={() => undefined}
        entityKind="Risk model"
        entityLabel="Risk model g-1"
        workflowName="wf-1"
        namespace="ns"
      />,
    )

    await waitFor(() => expect(screen.getByText('Failed to load workflow')).toBeInTheDocument())
  })

  it('shows an empty state when the workflow has no pod-backed steps', async () => {
    fetchWorkflowMock.mockResolvedValue({
      metadata: { name: 'wf-empty', namespace: 'ns' },
      status: { phase: 'Succeeded', nodes: {} },
    })

    render(
      <WorkflowStepsDialog
        open
        onClose={() => undefined}
        entityKind="Backtest"
        entityLabel="Backtest empty"
        workflowName="wf-empty"
        namespace="ns"
      />,
    )

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('No workflow steps were returned for this workflow.'),
    )
  })
})
