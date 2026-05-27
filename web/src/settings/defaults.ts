import type { PlatformSettings } from '../types/settings'

export const defaultPlatformSettings: PlatformSettings = {
  appearance: {
    theme_preset: 'default',
    theme_mode: 'dark',
    density: 'comfortable',
    chart_up_color: '#26a69a',
    chart_down_color: '#ef5350',
    chart_grid_visible: true,
    indicator_contrast: 'balanced',
    layout_width: 'standard',
    reduced_motion: false,
    time_display_format: '24h',
  },
  backtest_defaults: {
    symbols_seed_list: ['AAPL'],
    date_range_preset: '30D',
    resolution: '1d',
    feed: 'iex',
    broker: {
      cash: 10000,
      commission: 0,
      slippage_perc: 0.0005,
      sizer: 'fixed',
    },
    analyzers: {
      include_equity_curve: false,
      include_trade_log: true,
      include_order_log: true,
      include_candidate_log: false,
    },
    execution: {
      fill_model: 'close',
    },
  },
  live_defaults: {
    include_candidate_log: false,
  },
  platform_behavior: {
    timezone: 'America/New_York',
    auto_refresh_interval_seconds: 1.5,
    confirm_before_launch: false,
    preferred_landing_page: 'backtests',
    backtest_execution_backend: 'local',
    argo_split_by: 'symbol_strategy',
  },
}
