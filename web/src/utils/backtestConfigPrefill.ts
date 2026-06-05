import type {
  BacktestCreateRequest,
  BacktestFeed,
  BacktestModelPolicyInput,
} from '../types/backtests'
import type { BacktestListItem } from '../types/backtests'
import type { Resolution } from '../types/marketData'

export interface BacktestWizardPrefill {
  startDate: string
  endDate: string
  resolution: Resolution
  feed: BacktestFeed
  symbols: string[]
  triggers: Array<{ name: string; params: Record<string, unknown> }>
  exitRules: Array<{ name: string; params: Record<string, unknown> }>
  modelPolicy?: BacktestModelPolicyInput | null
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
  const { include_equity_curve, include_trade_log, include_order_log, include_candidate_log, include_risk_auxiliary } = value
  if (
    typeof include_equity_curve !== 'boolean' ||
    typeof include_trade_log !== 'boolean' ||
    typeof include_order_log !== 'boolean' ||
    typeof include_candidate_log !== 'boolean' ||
    typeof include_risk_auxiliary !== 'boolean'
  ) {
    return undefined
  }
  return {
    include_equity_curve,
    include_trade_log,
    include_order_log,
    include_candidate_log: include_risk_auxiliary ? true : include_candidate_log,
    include_risk_auxiliary,
  }
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

function parseModelArtifactRef(value: unknown): BacktestModelPolicyInput['forecast_model'] {
  if (!isRecord(value)) {
    return undefined
  }
  const groupId = typeof value.group_id === 'string' && value.group_id.trim() ? value.group_id.trim() : null
  const artifactPath =
    typeof value.model_artifact_path === 'string' && value.model_artifact_path.trim()
      ? value.model_artifact_path.trim()
      : null
  const targetKey = typeof value.target_key === 'string' && value.target_key.trim() ? value.target_key.trim() : null
  if (!groupId && !artifactPath) {
    return undefined
  }
  return {
    group_id: groupId,
    model_artifact_path: artifactPath,
    target_key: targetKey,
  }
}

function parseModelPolicy(value: unknown): BacktestModelPolicyInput | undefined {
  if (!isRecord(value)) {
    return undefined
  }
  const forecast_model = parseModelArtifactRef(value.forecast_model)
  const risk_model = parseModelArtifactRef(value.risk_model)
  if (
    forecast_model === undefined &&
    risk_model === undefined &&
    typeof value.threshold_bps !== 'number' &&
    typeof value.target_edge_bps !== 'number' &&
    typeof value.max_risk_fraction !== 'number' &&
    typeof value.allow_short !== 'boolean' &&
    typeof value.min_signal_score !== 'number'
  ) {
    return undefined
  }
  const modelPolicy: BacktestModelPolicyInput = {}
  if (forecast_model !== undefined) {
    modelPolicy.forecast_model = forecast_model
  }
  if (risk_model !== undefined) {
    modelPolicy.risk_model = risk_model
  }
  if (typeof value.threshold_bps === 'number') {
    modelPolicy.threshold_bps = value.threshold_bps
  }
  if (typeof value.target_edge_bps === 'number') {
    modelPolicy.target_edge_bps = value.target_edge_bps
  }
  if (typeof value.max_risk_fraction === 'number') {
    modelPolicy.max_risk_fraction = value.max_risk_fraction
  }
  if (typeof value.allow_short === 'boolean') {
    modelPolicy.allow_short = value.allow_short
  }
  if (typeof value.min_signal_score === 'number') {
    modelPolicy.min_signal_score = value.min_signal_score
  }
  return modelPolicy
}

export function parseInputConfigToPrefill(
  inputConfig: Record<string, unknown>,
): BacktestWizardPrefill | null {
  const runsRaw = inputConfig.runs
  if (!Array.isArray(runsRaw) || runsRaw.length === 0) {
    return null
  }

  const symbols: string[] = []
  const triggerNames: string[] = []
  const triggerParamsByName = new Map<string, Record<string, unknown>>()
  const exitRuleNames: string[] = []
  const exitRuleParamsByName = new Map<string, Record<string, unknown>>()
  let startDate: string | null = null
  let endDate: string | null = null
  let resolution: Resolution | null = null
  let feed: BacktestFeed | null = null
  let broker: BacktestCreateRequest['broker'] | undefined
  let analyzers: BacktestCreateRequest['analyzers'] | undefined
  let execution: BacktestCreateRequest['execution'] | undefined
  let modelPolicy: BacktestModelPolicyInput | undefined

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

    // New config: "trigger" + "exit_rules"
    const trigger = runRaw.trigger
    if (isRecord(trigger) && typeof trigger.name === 'string') {
      const name = trigger.name
      if (!triggerNames.includes(name)) {
        triggerNames.push(name)
        triggerParamsByName.set(name, isRecord(trigger.params) ? trigger.params : {})
      }
    } else {
      // Legacy config: "strategy" + "strategy_params"
      const legacyStrategy = runRaw.strategy
      if (typeof legacyStrategy === 'string' && !triggerNames.includes(legacyStrategy)) {
        triggerNames.push(legacyStrategy)
        if (isRecord(runRaw.strategy_params)) {
          triggerParamsByName.set(legacyStrategy, runRaw.strategy_params)
        } else {
          triggerParamsByName.set(legacyStrategy, {})
        }
      }
    }

    // New config: exit_rules is a selection object: { rules: [{name, params}, ...] }
    // Wizard supports a single ordered rule set; we prefill from the first run that provides one.
    if (exitRuleNames.length === 0) {
      const exitRules = runRaw.exit_rules
      if (isRecord(exitRules) && Array.isArray(exitRules.rules)) {
        for (const rule of exitRules.rules) {
          if (!isRecord(rule) || typeof rule.name !== 'string') {
            continue
          }
          if (exitRuleNames.includes(rule.name)) {
            continue
          }
          exitRuleNames.push(rule.name)
          exitRuleParamsByName.set(rule.name, isRecord(rule.params) ? rule.params : {})
        }
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
    if (modelPolicy === undefined) {
      modelPolicy = parseModelPolicy(runRaw.model_policy)
    }
  }

  if (
    startDate === null ||
    endDate === null ||
    resolution === null ||
    feed === null ||
    symbols.length === 0 ||
    triggerNames.length === 0 ||
    exitRuleNames.length === 0
  ) {
    return null
  }

  return {
    startDate,
    endDate,
    resolution,
    feed,
    symbols,
    triggers: triggerNames.map((name) => ({
      name,
      params: triggerParamsByName.get(name) ?? {},
    })),
    exitRules: exitRuleNames.map((name) => ({
      name,
      params: exitRuleParamsByName.get(name) ?? {},
    })),
    broker,
    analyzers,
    execution,
    modelPolicy,
  }
}

export function hasPrefillableInputConfig(inputConfig: Record<string, unknown> | undefined): boolean {
  if (!inputConfig) {
    return false
  }
  const runs = inputConfig.runs
  return Array.isArray(runs) && runs.length > 0
}

function isTerminalBacktestStatus(status: BacktestListItem['status']): boolean {
  return status === 'completed' || status === 'failed'
}

export function isRetryEligibleFailure(metadata: BacktestListItem): boolean {
  if (!isTerminalBacktestStatus(metadata.status)) {
    return false
  }
  if (metadata.status === 'failed') {
    return true
  }
  return metadata.report_status === 'partial_failure' || metadata.report_status === 'failure'
}

export function canRetryBacktest(metadata: BacktestListItem): boolean {
  if (metadata.status === 'pending' || metadata.status === 'running') {
    return true
  }
  return isRetryEligibleFailure(metadata)
}

export function canEditAndRetryBacktest(
  metadata: BacktestListItem,
  reportInputConfig: Record<string, unknown> | undefined,
): boolean {
  if (hasPrefillableInputConfig(reportInputConfig)) {
    return true
  }
  return metadata.selection !== null
}
