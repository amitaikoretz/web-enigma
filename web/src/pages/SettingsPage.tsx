import RestartAltIcon from '@mui/icons-material/RestartAlt'
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined'
import TuneIcon from '@mui/icons-material/Tune'
import WallpaperOutlinedIcon from '@mui/icons-material/WallpaperOutlined'
import WidgetsOutlinedIcon from '@mui/icons-material/WidgetsOutlined'
import {
  Alert,
  Box,
  Button,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'

import { fetchServerInfo } from '../api/serverInfo'
import { defaultPlatformSettings } from '../settings/defaults'
import { useSettings } from '../settings/useSettings'
import type { AppearanceSettings, PlatformSettings } from '../types/settings'
import type { ServerInfo } from '../types/serverInfo'

type SettingsTab = 'appearance' | 'backtests' | 'behavior'

export function SettingsPage() {
  const {
    appearance,
    platformSettings,
    loading,
    saving,
    error,
    patchAppearance,
    resetAppearance,
    savePlatformSettings,
  } = useSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>('appearance')
  const [draftOverride, setDraftOverride] = useState<PlatformSettings | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)
  const [serverInfoError, setServerInfoError] = useState<string | null>(null)
  const draft = draftOverride ?? platformSettings

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const next = await fetchServerInfo()
        if (!cancelled) {
          setServerInfo(next)
          setServerInfoError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setServerInfo(null)
          setServerInfoError(err instanceof Error ? err.message : 'Failed to load server info')
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  const handleAppearanceChange = <K extends keyof AppearanceSettings>(
    key: K,
    value: AppearanceSettings[K],
  ) => {
    setSaveMessage(null)
    patchAppearance({ [key]: value })
  }

  const handleDraftChange = (next: PlatformSettings) => {
    setSaveMessage(null)
    setDraftOverride(next)
  }

  const handleSave = async () => {
    try {
      await savePlatformSettings({
        ...draft,
        appearance,
      })
      setDraftOverride(null)
      setSaveMessage('Platform settings saved.')
    } catch {
      setSaveMessage(null)
    }
  }

  const handleResetPlatform = () => {
    setSaveMessage(null)
    setDraftOverride({
      ...defaultPlatformSettings,
      appearance,
    })
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Settings</Typography>
        <Typography color="text.secondary">
          Tune the platform’s defaults, behavior, and visual style in one place.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}
      {saveMessage && <Alert severity="success">{saveMessage}</Alert>}

      <Paper sx={{ p: 1.5 }}>
        <Tabs
          value={activeTab}
          onChange={(_event, nextValue: SettingsTab) => setActiveTab(nextValue)}
          variant="scrollable"
          allowScrollButtonsMobile
        >
          <Tab icon={<WallpaperOutlinedIcon />} iconPosition="start" value="appearance" label="Appearance" />
          <Tab icon={<TuneIcon />} iconPosition="start" value="backtests" label="Backtest Defaults" />
          <Tab icon={<WidgetsOutlinedIcon />} iconPosition="start" value="behavior" label="Platform Behavior" />
        </Tabs>
      </Paper>

      {activeTab === 'appearance' && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={3}>
            <SectionTitle
              title="Appearance"
              subtitle="Changes here apply immediately and stay on this device."
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
              <SelectField
                label="Theme preset"
                value={appearance.theme_preset}
                onChange={(value) => handleAppearanceChange('theme_preset', value as AppearanceSettings['theme_preset'])}
                options={[
                  ['default', 'Default Standard'],
                  ['alpine', 'Alpine Frost (Glacial Light)'],
                  ['solaris', 'Solaris Amber (Basalt Dark)'],
                  ['aurora', 'Aurora Mirage (Glassmorphic Glow)'],
                ]}
              />
              <SelectField
                label="Theme mode"
                value={appearance.theme_mode}
                onChange={(value) => handleAppearanceChange('theme_mode', value as AppearanceSettings['theme_mode'])}
                options={[
                  ['dark', 'Dark'],
                  ['light', 'Light'],
                  ['system', 'System'],
                ]}
              />
              <SelectField
                label="Density"
                value={appearance.density}
                onChange={(value) => handleAppearanceChange('density', value as AppearanceSettings['density'])}
                options={[
                  ['comfortable', 'Comfortable'],
                  ['compact', 'Compact'],
                ]}
              />
              <TextField
                label="Chart up color"
                value={appearance.chart_up_color}
                onChange={(event) => handleAppearanceChange('chart_up_color', event.target.value)}
              />
              <TextField
                label="Chart down color"
                value={appearance.chart_down_color}
                onChange={(event) => handleAppearanceChange('chart_down_color', event.target.value)}
              />
              <SelectField
                label="Indicator contrast"
                value={appearance.indicator_contrast}
                onChange={(value) =>
                  handleAppearanceChange(
                    'indicator_contrast',
                    value as AppearanceSettings['indicator_contrast'],
                  )
                }
                options={[
                  ['balanced', 'Balanced'],
                  ['high', 'High'],
                ]}
              />
              <SelectField
                label="Layout width"
                value={appearance.layout_width}
                onChange={(value) =>
                  handleAppearanceChange('layout_width', value as AppearanceSettings['layout_width'])
                }
                options={[
                  ['standard', 'Standard'],
                  ['wide', 'Wide'],
                ]}
              />
              <SelectField
                label="Time display format"
                value={appearance.time_display_format}
                onChange={(value) =>
                  handleAppearanceChange(
                    'time_display_format',
                    value as AppearanceSettings['time_display_format'],
                  )
                }
                options={[
                  ['12h', '12h'],
                  ['24h', '24h'],
                ]}
              />
            </Box>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={appearance.chart_grid_visible}
                    onChange={(_event, checked) => handleAppearanceChange('chart_grid_visible', checked)}
                  />
                }
                label="Show chart grid"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={appearance.reduced_motion}
                    onChange={(_event, checked) => handleAppearanceChange('reduced_motion', checked)}
                  />
                }
                label="Reduced motion"
              />
            </Stack>
            <Box>
              <Button variant="outlined" startIcon={<RestartAltIcon />} onClick={resetAppearance}>
                Reset appearance
              </Button>
            </Box>
          </Stack>
        </Paper>
      )}

      {activeTab === 'backtests' && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={3}>
            <SectionTitle
              title="Backtest Defaults"
              subtitle="These defaults prefill new jobs and provide the API fallback for optional execution fields."
            />
            {serverInfoError && <Alert severity="warning">{serverInfoError}</Alert>}
            <TextField
              label="Backtest storage directory"
              value={serverInfo?.backtest_results_dir ?? (loading ? 'Loading…' : 'Unavailable')}
              helperText="Reports (.json), metadata (.meta.json), and saved configs (.yaml) are loaded and written here by the API server."
              slotProps={{
                input: {
                  readOnly: true,
                },
              }}
              fullWidth
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
              <TextField
                label="Seed symbols"
                value={draft.backtest_defaults.symbols_seed_list.join(', ')}
                helperText="Comma-separated symbols used to prefill the wizard."
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      symbols_seed_list: event.target.value
                        .split(',')
                        .map((item) => item.trim().toUpperCase())
                        .filter(Boolean),
                    },
                  })
                }
              />
              <SelectField
                label="Date range preset"
                value={draft.backtest_defaults.date_range_preset}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      date_range_preset: value as PlatformSettings['backtest_defaults']['date_range_preset'],
                    },
                  })
                }
                options={[
                  ['30D', '30 days'],
                  ['90D', '90 days'],
                  ['1Y', '1 year'],
                ]}
              />
              <SelectField
                label="Resolution"
                value={draft.backtest_defaults.resolution}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      resolution: value as PlatformSettings['backtest_defaults']['resolution'],
                    },
                  })
                }
                options={[
                  ['1m', '1m'],
                  ['5m', '5m'],
                  ['15m', '15m'],
                  ['1h', '1h'],
                  ['1d', '1d'],
                ]}
              />
              <SelectField
                label="Feed"
                value={draft.backtest_defaults.feed}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      feed: value as PlatformSettings['backtest_defaults']['feed'],
                    },
                  })
                }
                options={[
                  ['iex', 'iex'],
                  ['sip', 'sip'],
                  ['otc', 'otc'],
                ]}
              />
              <TextField
                label="Broker cash"
                type="number"
                value={draft.backtest_defaults.broker.cash}
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      broker: {
                        ...draft.backtest_defaults.broker,
                        cash: Number(event.target.value),
                      },
                    },
                  })
                }
              />
              <TextField
                label="Commission"
                type="number"
                value={draft.backtest_defaults.broker.commission}
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      broker: {
                        ...draft.backtest_defaults.broker,
                        commission: Number(event.target.value),
                      },
                    },
                  })
                }
              />
              <TextField
                label="Slippage %"
                type="number"
                value={draft.backtest_defaults.broker.slippage_perc}
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      broker: {
                        ...draft.backtest_defaults.broker,
                        slippage_perc: Number(event.target.value),
                      },
                    },
                  })
                }
              />
              <SelectField
                label="Fill model"
                value={draft.backtest_defaults.execution.fill_model}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    backtest_defaults: {
                      ...draft.backtest_defaults,
                      execution: {
                        fill_model: value as PlatformSettings['backtest_defaults']['execution']['fill_model'],
                      },
                    },
                  })
                }
                options={[
                  ['close', 'close'],
                  ['next_bar', 'next_bar'],
                ]}
              />
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.backtest_defaults.analyzers.include_equity_curve}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        backtest_defaults: {
                          ...draft.backtest_defaults,
                          analyzers: {
                            ...draft.backtest_defaults.analyzers,
                            include_equity_curve: checked,
                          },
                        },
                      })
                    }
                  />
                }
                label="Include equity curve"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.backtest_defaults.analyzers.include_trade_log}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        backtest_defaults: {
                          ...draft.backtest_defaults,
                          analyzers: {
                            ...draft.backtest_defaults.analyzers,
                            include_trade_log: checked,
                          },
                        },
                      })
                    }
                  />
                }
                label="Include trade log"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.backtest_defaults.analyzers.include_order_log}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        backtest_defaults: {
                          ...draft.backtest_defaults,
                          analyzers: {
                            ...draft.backtest_defaults.analyzers,
                            include_order_log: checked,
                          },
                        },
                      })
                    }
                  />
                }
                label="Include order log"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.backtest_defaults.analyzers.include_candidate_log}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        backtest_defaults: {
                          ...draft.backtest_defaults,
                          analyzers: {
                            ...draft.backtest_defaults.analyzers,
                            include_candidate_log: checked,
                          },
                        },
                      })
                    }
                  />
                }
                label="Include candidate log"
              />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Candidate logging records entry candidates (traded and rejected) for risk-model dataset
              building. It increases backtest output size.
            </Typography>
            <Stack spacing={2}>
              <Typography variant="subtitle1">Live trading</Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.live_defaults.include_candidate_log}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        live_defaults: {
                          ...draft.live_defaults,
                          include_candidate_log: checked,
                        },
                      })
                    }
                  />
                }
                label="Log live entry candidates"
              />
              <Typography variant="body2" color="text.secondary">
                Appends candidate events to the live runtime state directory for later labeling and
                calibration.
              </Typography>
            </Stack>
          </Stack>
        </Paper>
      )}

      {activeTab === 'behavior' && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={3}>
            <SectionTitle
              title="Platform Behavior"
              subtitle="These settings affect routing, refresh cadence, and default timestamp presentation."
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
              <TextField
                label="Timezone"
                value={draft.platform_behavior.timezone}
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    platform_behavior: {
                      ...draft.platform_behavior,
                      timezone: event.target.value,
                    },
                  })
                }
              />
              <TextField
                label="Auto-refresh interval (seconds)"
                type="number"
                value={draft.platform_behavior.auto_refresh_interval_seconds}
                onChange={(event) =>
                  handleDraftChange({
                    ...draft,
                    platform_behavior: {
                      ...draft.platform_behavior,
                      auto_refresh_interval_seconds: Number(event.target.value),
                    },
                  })
                }
              />
              <SelectField
                label="Preferred landing page"
                value={draft.platform_behavior.preferred_landing_page}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    platform_behavior: {
                      ...draft.platform_behavior,
                      preferred_landing_page:
                        value as PlatformSettings['platform_behavior']['preferred_landing_page'],
                    },
                  })
                }
                options={[
                  ['backtests', 'Backtests'],
                  ['new_backtest', 'New Backtest'],
                  ['chart', 'Chart'],
                ]}
              />
            </Box>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={draft.platform_behavior.confirm_before_launch}
                    onChange={(_event, checked) =>
                      handleDraftChange({
                        ...draft,
                        platform_behavior: {
                          ...draft.platform_behavior,
                          confirm_before_launch: checked,
                        },
                      })
                    }
                  />
                }
                label="Confirm before launching a backtest"
              />
            </Stack>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
              <SelectField
                label="Backtest execution backend"
                value={draft.platform_behavior.backtest_execution_backend}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    platform_behavior: {
                      ...draft.platform_behavior,
                      backtest_execution_backend:
                        value as PlatformSettings['platform_behavior']['backtest_execution_backend'],
                    },
                  })
                }
                options={[
                  ['local', 'Local (in-process)'],
                  ['argo', 'Argo Workflows'],
                ]}
              />
              <SelectField
                label="Argo split strategy"
                value={draft.platform_behavior.argo_split_by}
                onChange={(value) =>
                  handleDraftChange({
                    ...draft,
                    platform_behavior: {
                      ...draft.platform_behavior,
                      argo_split_by: value as PlatformSettings['platform_behavior']['argo_split_by'],
                    },
                  })
                }
                options={[
                  ['run', 'By run entry'],
                  ['symbol', 'By symbol'],
                  ['strategy', 'By strategy'],
                  ['symbol_strategy', 'By symbol + strategy'],
                ]}
                disabled={draft.platform_behavior.backtest_execution_backend !== 'argo'}
              />
            </Box>
          </Stack>
        </Paper>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between' }}>
        <Button variant="outlined" startIcon={<RestartAltIcon />} onClick={handleResetPlatform}>
          Reset platform defaults
        </Button>
        <Button
          variant="contained"
          startIcon={<SaveOutlinedIcon />}
          onClick={() => void handleSave()}
          disabled={loading || saving}
        >
          {saving ? 'Saving…' : 'Save platform settings'}
        </Button>
      </Stack>
    </Stack>
  )
}

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="h6">{title}</Typography>
      <Typography color="text.secondary">{subtitle}</Typography>
    </Stack>
  )
}

function SelectField({
  label,
  value,
  onChange,
  options,
  disabled = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: Array<[string, string]>
  disabled?: boolean
}) {
  return (
    <FormControl fullWidth disabled={disabled}>
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => (
          <MenuItem key={optionValue} value={optionValue}>
            {optionLabel}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}
