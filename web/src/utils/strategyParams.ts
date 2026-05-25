import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'

export function defaultValueForParam(meta: StrategyParameterMetadata): unknown {
  if (meta.default !== undefined && meta.default !== null) {
    return meta.default
  }
  if (meta.type === 'boolean') {
    return false
  }
  if (meta.type === 'integer' || meta.type === 'number') {
    return meta.minimum ?? 0
  }
  return ''
}

export function buildDefaultParams(strategy: StrategyMetadata | null): Record<string, unknown> {
  if (!strategy) {
    return {}
  }
  return Object.fromEntries(
    Object.entries(strategy.parameters).map(([name, meta]) => [name, defaultValueForParam(meta)]),
  )
}

export function parseParamValue(meta: StrategyParameterMetadata, raw: string): unknown {
  if (meta.type === 'boolean') {
    return raw === 'true'
  }
  if (meta.type === 'integer') {
    return Number.parseInt(raw, 10)
  }
  if (meta.type === 'number') {
    return Number.parseFloat(raw)
  }
  return raw
}

export function normalizeParamValue(meta: StrategyParameterMetadata, value: unknown): unknown {
  if (meta.type === 'boolean') {
    return Boolean(value)
  }
  if (meta.type === 'integer' || meta.type === 'number') {
    return parseParamValue(meta, String(value ?? ''))
  }
  return value ?? ''
}

export function buildOverrideParams(
  strategy: StrategyMetadata,
  params: Record<string, unknown>,
): Record<string, unknown> {
  const overrides: Record<string, unknown> = {}
  for (const [name, meta] of Object.entries(strategy.parameters)) {
    const currentValue = params[name]
    const defaultValue = defaultValueForParam(meta)
    if (currentValue === '' || currentValue === null || currentValue === undefined) {
      continue
    }
    if (typeof currentValue === 'number' && Number.isNaN(currentValue)) {
      continue
    }
    if (currentValue !== defaultValue) {
      overrides[name] = currentValue
    }
  }
  return overrides
}
