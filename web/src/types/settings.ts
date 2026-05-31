import type { BacktestFeed } from './backtests'
import type { Resolution } from './marketData'

export type ThemeModePreference = 'dark' | 'light' | 'system'
export type ThemePreset =
  | 'default'
  | 'alpine'
  | 'fjord'
  | 'fjord_porcelain'
  | 'oslo'
  | 'helsinki'
  | 'polar'
  | 'frost'
  | 'silica'
  | 'alto'
  | 'glacial'
  | 'glacier_lilac'
  | 'graphite_teal'
  | 'solaris'
  | 'aurora'
  | 'fjord_ink_fx'
  | 'deep_fjord_fx'
  | 'aurora_slate'
  | 'obsidian_cobalt'
  | 'plum_neon'
  | 'steel_ember'
export type DensityPreference = 'comfortable' | 'compact'
export type LayoutWidthPreference = 'standard' | 'wide'
export type TimeDisplayFormat = '12h' | '24h'
export type IndicatorContrast = 'balanced' | 'high'
export type DateRangePreset = '30D' | '90D' | '1Y'
export type PreferredLandingPage = 'backtests' | 'new_backtest' | 'chart'

export interface AppearanceSettings {
  theme_preset: ThemePreset
  theme_mode: ThemeModePreference
  density: DensityPreference
  chart_up_color: string
  chart_down_color: string
  chart_grid_visible: boolean
  indicator_contrast: IndicatorContrast
  layout_width: LayoutWidthPreference
  reduced_motion: boolean
  time_display_format: TimeDisplayFormat
}

export interface BrokerSettings {
  cash: number
  commission: number
  slippage_perc: number
  sizer: 'fixed'
}

export interface AnalyzerSettings {
  include_equity_curve: boolean
  include_trade_log: boolean
  include_order_log: boolean
  include_candidate_log: boolean
  include_risk_auxiliary: boolean
}

export interface ExecutionSettings {
  fill_model: 'close' | 'next_bar'
}

export type BacktestResultsColumnId =
  | 'name'
  | 'created'
  | 'status'
  | 'report'
  | 'artifacts'
  | 'date_range'
  | 'universe'
  | 'runs'
  | 'runtime'
  | 'json'
  | 'yaml'

export interface BacktestDefaults {
  symbols_seed_list: string[]
  date_range_preset: DateRangePreset
  resolution: Resolution
  feed: BacktestFeed
  broker: BrokerSettings
  analyzers: AnalyzerSettings
  execution: ExecutionSettings
  results_table_columns: BacktestResultsColumnId[]
}

export type BacktestExecutionBackend = 'local' | 'argo'
export type ArgoSplitBy = 'run' | 'symbol' | 'strategy' | 'symbol_strategy'

export interface PlatformBehaviorSettings {
  timezone: string
  auto_refresh_interval_seconds: number
  confirm_before_launch: boolean
  preferred_landing_page: PreferredLandingPage
  backtest_execution_backend: BacktestExecutionBackend
  argo_split_by: ArgoSplitBy
}

export interface LiveDefaults {
  include_candidate_log: boolean
}

export interface ServerPlatformSettings {
  backtest_defaults: BacktestDefaults
  live_defaults: LiveDefaults
  platform_behavior: PlatformBehaviorSettings
}

export interface PlatformSettings extends ServerPlatformSettings {
  appearance: AppearanceSettings
}
