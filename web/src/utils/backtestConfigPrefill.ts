import type { BacktestCreateRequest, BacktestFeed } from '../types/backtests'
import type { Resolution } from '../types/marketData'

export interface BacktestWizardPrefill {
  startDate: string
  endDate: string
  resolution: Resolution
  feed: BacktestFeed
  symbols: string[]
  strategies: Array<{ name: string; params: Record<string, unknown> }>
  broker?: BacktestCreateRequest['broker']
  analyzers?: BacktestCreateRequest['analyzers']
  execution?: BacktestCreateRequest['execution']
}

const VALID_RESOLUTIONS = new Set<Resolution>(['1m', '5m', '15m', '1h', '1d'])
const VALID_FEEDS = new Set<BacktestFeed>(['iex', 'sip', 'otc'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseBroker(value: unknown): BacktestCreateRequest['broker'] | undefined {
  if (!isRecord(value)) {
    return undefined
  }
  const { cash, commission, slippage_perc, sizer } = value
  if (
    typeof cash !== 'number' ||
    typeof commission !== 'number' ||
    typeof slippage_perc !== 'number' ||
    sizer !== 'fixed'
  ) {
    return undefined
  }
  return { cash, commission, slippage_perc, sizer }
}

function parseAnalyzers(value: unknown): BacktestCreateRequest['analyzers'] | undefined {
  if (!isRecord(value)) {
    return undefined
  }
  const { include_equity_curve, include_trade_log, include_order_log, include_candidate_log } = value
  if (
    typeof include_equity_curve !== 'boolean' ||
    typeof include_trade_log !== 'boolean' ||
    typeof include_order_log !== 'boolean' ||
    typeof include_candidate_log !== 'boolean'
  ) {
    return undefined
  }
  return { include_equity_curve, include_trade_log, include_order_log, include_candidate_log }
}

function parseExecution(value: unknown): BacktestCreateRequest['execution'] | undefined {
  if (!isRecord(value)) {
    return undefined
  }
  const { fill_model } = value
  if (fill_model !== 'close' && fill_model !== 'next_bar') {
    return undefined
  }
  return { fill_model }
}

export function parseInputConfigToPrefill(
  inputConfig: Record<string, unknown>,
): BacktestWizardPrefill | null {
  const runsRaw = inputConfig.runs
  if (!Array.isArray(runsRaw) || runsRaw.length === 0) {
    return null
  }

  const symbols: string[] = []
  const strategyNames: string[] = []
  const strategyParamsByName = new Map<string, Record<string, unknown>>()
  let startDate: string | null = null
  let endDate: string | null = null
  let resolution: Resolution | null = null
  let feed: BacktestFeed | null = null
  let broker: BacktestCreateRequest['broker'] | undefined
  let analyzers: BacktestCreateRequest['analyzers'] | undefined
  let execution: BacktestCreateRequest['execution'] | undefined

  for (const runRaw of runsRaw) {
    if (!isRecord(runRaw)) {
      continue
    }

    if (startDate === null && typeof runRaw.start_date === 'string') {
      startDate = runRaw.start_date
    }
    if (typeof runRaw.end_date === 'string') {
      endDate = runRaw.end_date
    }

    const data = runRaw.data
    if (isRecord(data)) {
      const symbol = data.symbol
      if (typeof symbol === 'string' && !symbols.includes(symbol)) {
        symbols.push(symbol)
      }
      const interval = data.interval
      if (typeof interval === 'string' && VALID_RESOLUTIONS.has(interval as Resolution)) {
        resolution = interval as Resolution
      }
      const runFeed = data.feed
      if (typeof runFeed === 'string' && VALID_FEEDS.has(runFeed as BacktestFeed)) {
        feed = runFeed as BacktestFeed
      }
    }

    const strategy = runRaw.strategy
    if (typeof strategy === 'string' && !strategyNames.includes(strategy)) {
      strategyNames.push(strategy)
      if (isRecord(runRaw.strategy_params)) {
        strategyParamsByName.set(strategy, runRaw.strategy_params)
      } else {
        strategyParamsByName.set(strategy, {})
      }
    }

    if (broker === undefined) {
      broker = parseBroker(runRaw.broker)
    }
    if (analyzers === undefined) {
      analyzers = parseAnalyzers(runRaw.analyzers)
    }
    if (execution === undefined) {
      execution = parseExecution(runRaw.execution)
    }
  }

  if (
    startDate === null ||
    endDate === null ||
    resolution === null ||
    feed === null ||
    symbols.length === 0 ||
    strategyNames.length === 0
  ) {
    return null
  }

  return {
    startDate,
    endDate,
    resolution,
    feed,
    symbols,
    strategies: strategyNames.map((name) => ({
      name,
      params: strategyParamsByName.get(name) ?? {},
    })),
    broker,
    analyzers,
    execution,
  }
}

export function hasPrefillableInputConfig(inputConfig: Record<string, unknown> | undefined): boolean {
  if (!inputConfig) {
    return false
  }
  const runs = inputConfig.runs
  return Array.isArray(runs) && runs.length > 0
}
