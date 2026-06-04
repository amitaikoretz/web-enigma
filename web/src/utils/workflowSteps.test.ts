import { describe, expect, it } from 'vitest'

import { normalizeWorkflowSteps } from './workflowSteps'

describe('normalizeWorkflowSteps', () => {
  it('keeps the Argo node name separate from the real pod name', () => {
    const steps = normalizeWorkflowSteps({
      metadata: { name: 'wf-1', namespace: 'ns' },
      status: {
        nodes: {
          'node-1': {
            id: 'node-1',
            name: 'backtest-e193fd02fd61-f96c23[0].print-payload',
            displayName: 'print-payload',
            phase: 'Succeeded',
            templateName: 'print-payload',
            podName: 'backtest-e193fd02fd61-f96c23-abc123',
            outputs: {
              parameters: [{ name: 'terminal-command', value: 'python -m app.standalone.print_argo_payload' }],
            },
          },
        },
      },
    })

    expect(steps).toHaveLength(1)
    expect(steps[0]?.name).toBe('backtest-e193fd02fd61-f96c23[0].print-payload')
    expect(steps[0]?.podName).toBe('backtest-e193fd02fd61-f96c23-abc123')
    expect(steps[0]?.displayName).toBe('print-payload')
  })

  it('derives the pod name from the node name when Argo omits podName', () => {
    const steps = normalizeWorkflowSteps({
      metadata: { name: 'wf-2', namespace: 'ns' },
      status: {
        nodes: {
          'node-1': {
            id: 'node-1',
            name: 'backtest-e193fd02fd61-f96c23[0].print-payload',
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

    expect(steps).toHaveLength(1)
    expect(steps[0]?.podName).toBe('backtest-e193fd02fd61-f96c23')
  })
})
