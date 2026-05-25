import type { Resolution } from '../types/marketData'
import type { StrategyMetadata } from '../types/strategies'
import { buildDefaultParams } from './strategyParams'

type StrategyPresetOverrides = Record<string, unknown>

const VOLUME_RALLY_PRESETS: Partial<Record<Resolution, StrategyPresetOverrides>> = {
  '1m': {
    stake: 10,
    volume_spike_mult: 3.0,
    trail_atr_mult: 2.0,
    cooldown_bars: 20,
    max_hold_bars: 48,
  },
  '5m': {
    stake: 10,
    volume_spike_mult: 3.0,
    trail_atr_mult: 1.5,
    cooldown_bars: 10,
    max_hold_bars: 48,
  },
  '1d': {
    cooldown_bars: 0,
  },
}

const STRATEGY_PRESETS: Record<string, Partial<Record<Resolution, StrategyPresetOverrides>>> = {
  volume_rally: VOLUME_RALLY_PRESETS,
}

export function strategyPresetOverrides(
  strategyName: string,
  resolution: Resolution,
): StrategyPresetOverrides {
  return STRATEGY_PRESETS[strategyName]?.[resolution] ?? {}
}

export function buildStrategyParams(
  strategy: StrategyMetadata | null,
  resolution: Resolution,
): Record<string, unknown> {
  const defaults = buildDefaultParams(strategy)
  if (!strategy) {
    return defaults
  }
  return {
    ...defaults,
    ...strategyPresetOverrides(strategy.name, resolution),
  }
}

const INTRADAY_RESOLUTIONS = new Set<Resolution>(['1m', '5m', '15m'])

export function shouldShowCommissionDragWarning(
  resolution: Resolution,
  commission: number,
  strategies: StrategyMetadata[],
  strategyOverrides: Record<string, Record<string, unknown>>,
): boolean {
  if (!INTRADAY_RESOLUTIONS.has(resolution) || commission < 0.001) {
    return false
  }
  return strategies.some((strategy) => {
    const params = strategyOverrides[strategy.name] ?? buildStrategyParams(strategy, resolution)
    const stake = Number(params.stake ?? strategy.parameters.stake?.default ?? 1)
    return stake <= 1
  })
}
