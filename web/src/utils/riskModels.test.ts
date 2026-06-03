import { describe, expect, it } from 'vitest'

import { isRiskModelActive, resolveRiskModelStatus, statusFromArgoPhase } from './riskModels'

describe('risk model status helpers', () => {
  it('maps Argo terminal phases to UI statuses', () => {
    expect(statusFromArgoPhase('Succeeded')).toBe('succeeded')
    expect(statusFromArgoPhase('Failed')).toBe('failed')
    expect(statusFromArgoPhase('Error')).toBe('failed')
    expect(statusFromArgoPhase('Running')).toBe('running')
  })

  it('keeps terminal database statuses stable', () => {
    expect(resolveRiskModelStatus('succeeded', 'Failed')).toBe('succeeded')
    expect(resolveRiskModelStatus('failed', 'Running')).toBe('failed')
  })

  it('treats only pending and running as active', () => {
    expect(isRiskModelActive('pending')).toBe(true)
    expect(isRiskModelActive('running')).toBe(true)
    expect(isRiskModelActive('failed')).toBe(false)
    expect(isRiskModelActive('succeeded')).toBe(false)
    expect(isRiskModelActive('canceled')).toBe(false)
  })
})
