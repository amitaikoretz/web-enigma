import TuneIcon from '@mui/icons-material/Tune'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createBacktest } from '../api/backtests'
import { fetchStrategies } from '../api/strategies'
import { useSettings } from '../settings/useSettings'
import type { BacktestFeed } from '../types/backtests'
import type { Resolution } from '../types/marketData'
import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'
import {
  buildOverrideParams,
  normalizeParamValue,
} from '../utils/strategyParams'
import {
  buildStrategyParams,
  shouldShowCommissionDragWarning,
} from '../utils/strategyPresets'

const RESOLUTIONS: Resolution[] = ['1m', '5m', '15m', '1h', '1d']
const FEEDS: BacktestFeed[] = ['iex', 'sip', 'otc']

function resolveStartDatePreset(value: '30D' | '90D' | '1Y'): Dayjs {
  if (value === '90D') {
    return dayjs().subtract(90, 'day')
  }
  if (value === '1Y') {
    return dayjs().subtract(1, 'year')
  }
  return dayjs().subtract(30, 'day')
}

function formatDateRange(startDate: Dayjs | null, endDate: Dayjs | null): string {
  if (!startDate || !endDate) {
    return 'Choose a start and end date.'
  }
  return `${startDate.format('MMM D, YYYY')} to ${endDate.format('MMM D, YYYY')}`
}

function ParameterField({
  name,
  meta,
  value,
  disabled,
  onChange,
}: {
  name: string
  meta: StrategyParameterMetadata
  value: unknown
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  if (meta.type === 'boolean') {
    return (
      <FormControl fullWidth size="small">
        <InputLabel id={`${name}-label`}>{name}</InputLabel>
        <Select
          labelId={`${name}-label`}
          label={name}
          value={String(Boolean(value))}
          onChange={(event) => onChange(event.target.value === 'true')}
          disabled={disabled}
        >
          <MenuItem value="true">true</MenuItem>
          <MenuItem value="false">false</MenuItem>
        </Select>
      </FormControl>
    )
  }

  return (
    <TextField
      label={name}
      size="small"
      type={meta.type === 'string' ? 'text' : 'number'}
      value={value ?? ''}
      onChange={(event) => onChange(normalizeParamValue(meta, event.target.value))}
      disabled={disabled}
      slotProps={{
        htmlInput: {
          min: meta.minimum ?? undefined,
          max: meta.maximum ?? undefined,
          step: meta.type === 'integer' ? 1 : 'any',
        },
      }}
      fullWidth
    />
  )
}

export function BacktestWizardPage() {
  const { platformSettings } = useSettings()
  const navigate = useNavigate()
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([])
  const [loadingStrategies, setLoadingStrategies] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [symbols, setSymbols] = useState<string[]>(platformSettings.backtest_defaults.symbols_seed_list)
  const [startDate, setStartDate] = useState<Dayjs | null>(
    resolveStartDatePreset(platformSettings.backtest_defaults.date_range_preset),
  )
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [resolution, setResolution] = useState<Resolution>(platformSettings.backtest_defaults.resolution)
  const [feed, setFeed] = useState<BacktestFeed>(platformSettings.backtest_defaults.feed)
  const [selectedStrategyNames, setSelectedStrategyNames] = useState<string[]>([])
  const [strategyOverrides, setStrategyOverrides] = useState<Record<string, Record<string, unknown>>>({})

  useEffect(() => {
    let cancelled = false
    fetchStrategies()
      .then((items) => {
        if (cancelled) {
          return
        }
        setStrategies(items)
        if (items[0]) {
          setSelectedStrategyNames([items[0].name])
          setStrategyOverrides({
            [items[0].name]: buildStrategyParams(items[0], platformSettings.backtest_defaults.resolution),
          })
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load strategies')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingStrategies(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const selectedStrategies = useMemo(
    () =>
      selectedStrategyNames
        .map((name) => strategies.find((strategy) => strategy.name === name) ?? null)
        .filter((strategy): strategy is StrategyMetadata => strategy !== null),
    [selectedStrategyNames, strategies],
  )

  const totalRuns = symbols.length * selectedStrategies.length
  const hasValidDateRange =
    startDate !== null && endDate !== null && !endDate.isBefore(startDate, 'day')

  const handleStrategySelectionChange = (nextStrategies: StrategyMetadata[]) => {
    const nextNames = nextStrategies.map((strategy) => strategy.name)
    setSelectedStrategyNames(nextNames)
    setStrategyOverrides((current) => {
      const nextOverrides: Record<string, Record<string, unknown>> = {}
      for (const strategy of nextStrategies) {
        nextOverrides[strategy.name] =
          current[strategy.name] ?? buildStrategyParams(strategy, resolution)
      }
      return nextOverrides
    })
  }

  const handleResolutionChange = (nextResolution: Resolution) => {
    setResolution(nextResolution)
    setStrategyOverrides((_current) => {
      const nextOverrides: Record<string, Record<string, unknown>> = {}
      for (const strategy of selectedStrategies) {
        nextOverrides[strategy.name] = buildStrategyParams(strategy, nextResolution)
      }
      return nextOverrides
    })
  }

  const showCommissionDragWarning = useMemo(
    () =>
      shouldShowCommissionDragWarning(
        resolution,
        platformSettings.backtest_defaults.broker.commission,
        selectedStrategies,
        strategyOverrides,
      ),
    [resolution, platformSettings.backtest_defaults.broker.commission, selectedStrategies, strategyOverrides],
  )

  const handleParamChange = (strategyName: string, name: string, value: unknown) => {
    setStrategyOverrides((current) => ({
      ...current,
      [strategyName]: {
        ...(current[strategyName] ?? {}),
        [name]: value,
      },
    }))
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!startDate || !endDate || !hasValidDateRange) {
      setError('Choose a valid date range before submitting.')
      return
    }
    if (symbols.length === 0 || selectedStrategies.length === 0) {
      setError('Add at least one symbol and one strategy before submitting.')
      return
    }

    if (platformSettings.platform_behavior.confirm_before_launch) {
      const confirmed = window.confirm(
        `Launch ${totalRuns} backtest run${totalRuns === 1 ? '' : 's'} using ${symbols.length} symbol${symbols.length === 1 ? '' : 's'} and ${selectedStrategies.length} strateg${selectedStrategies.length === 1 ? 'y' : 'ies'}?`,
      )
      if (!confirmed) {
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      const response = await createBacktest({
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        resolution,
        feed,
        symbols,
        strategies: selectedStrategies.map((strategy) => ({
          name: strategy.name,
          params: buildOverrideParams(strategy, strategyOverrides[strategy.name] ?? {}),
        })),
        broker: platformSettings.backtest_defaults.broker,
        analyzers: platformSettings.backtest_defaults.analyzers,
        execution: platformSettings.backtest_defaults.execution,
      })
      navigate(`/backtests/${response.backtest_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create backtest')
      setSubmitting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Backtest Wizard</Typography>
        <Typography color="text.secondary">
          Build a matrix of symbols and strategies, then let the API run it in the background.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Stack component="form" spacing={3} onSubmit={handleSubmit}>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="h6">Universe</Typography>
            </Stack>
            <Autocomplete
              multiple
              freeSolo
              options={[]}
              value={symbols}
              onChange={(_event, value) => {
                const nextSymbols = value
                  .map((item) => item.trim().toUpperCase())
                  .filter(Boolean)
                  .filter((item, index, values) => values.indexOf(item) === index)
                setSymbols(nextSymbols)
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Symbols"
                  placeholder="Type a symbol and press Enter"
                  helperText="Use chips to build a backtest basket."
                />
              )}
            />
          </Stack>
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Range and market data</Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <DatePicker
                label="Start date"
                value={startDate}
                onChange={setStartDate}
                slotProps={{ textField: { fullWidth: true } }}
              />
              <DatePicker
                label="End date"
                value={endDate}
                onChange={setEndDate}
                slotProps={{ textField: { fullWidth: true } }}
              />
              <FormControl fullWidth>
                <InputLabel id="resolution-label">Resolution</InputLabel>
                <Select
                  labelId="resolution-label"
                  label="Resolution"
                  value={resolution}
                  onChange={(event) => handleResolutionChange(event.target.value as Resolution)}
                >
                  {RESOLUTIONS.map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel id="feed-label">Feed</InputLabel>
                <Select
                  labelId="feed-label"
                  label="Feed"
                  value={feed}
                  onChange={(event) => setFeed(event.target.value as BacktestFeed)}
                >
                  {FEEDS.map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
            {showCommissionDragWarning && (
              <Alert severity="warning">
                Intraday backtests with stake of 1 share and commission of 0.1% per side often
                produce net losses even on small gross winners (~0.2% round-trip cost). Use stake
                of at least 10 or lower commission for more meaningful intraday results.
              </Alert>
            )}
          </Stack>
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <TuneIcon color="primary" />
              <Typography variant="h6">Strategies and optional overrides</Typography>
            </Stack>
            {loadingStrategies ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <CircularProgress size={20} />
                <Typography color="text.secondary">Loading strategies…</Typography>
              </Stack>
            ) : (
              <>
                <Autocomplete
                  multiple
                  options={strategies}
                  getOptionLabel={(option) => option.name}
                  value={selectedStrategies}
                  onChange={(_event, value) => handleStrategySelectionChange(value)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Strategies"
                      helperText="Choose one or more strategies to expand against the symbol list."
                    />
                  )}
                />

                {selectedStrategies.map((strategy) => {
                  const params =
                    strategyOverrides[strategy.name] ?? buildStrategyParams(strategy, resolution)
                  const overrideCount = Object.keys(buildOverrideParams(strategy, params)).length
                  const showVolumeRallyStakeHint =
                    strategy.name === 'volume_rally' &&
                    ['1m', '5m', '15m'].includes(resolution)
                  return (
                    <Paper
                      key={strategy.name}
                      variant="outlined"
                      sx={{ p: 2, bgcolor: 'background.default' }}
                    >
                      <Stack spacing={2}>
                        <Stack
                          direction={{ xs: 'column', sm: 'row' }}
                          spacing={1}
                          sx={{ justifyContent: 'space-between' }}
                        >
                          <Box>
                            <Typography variant="subtitle1">{strategy.name}</Typography>
                            <Typography variant="body2" color="text.secondary">
                              {strategy.description}
                            </Typography>
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            {overrideCount} override{overrideCount === 1 ? '' : 's'} applied
                          </Typography>
                        </Stack>
                        <Box
                          sx={{
                            display: 'grid',
                            gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                            gap: 2,
                          }}
                        >
                          {Object.entries(strategy.parameters).map(([name, meta]) => (
                            <ParameterField
                              key={`${strategy.name}-${name}`}
                              name={name}
                              meta={meta}
                              value={params[name]}
                              disabled={submitting}
                              onChange={(value) => handleParamChange(strategy.name, name, value)}
                            />
                          ))}
                        </Box>
                        {showVolumeRallyStakeHint && (
                          <Typography variant="caption" color="text.secondary">
                            volume_rally presets use 5m bars and stake 10 for intraday; IEX volume is
                            partial versus SIP.
                          </Typography>
                        )}
                      </Stack>
                    </Paper>
                  )
                })}
              </>
            )}
          </Stack>
        </Paper>

        <Paper
          sx={{
            p: 3,
            background:
              'linear-gradient(135deg, rgba(66,165,245,0.18) 0%, rgba(34,211,238,0.08) 100%)',
            border: 1,
            borderColor: 'divider',
          }}
        >
          <Stack spacing={2}>
            <Typography variant="h6">Review</Typography>
            <Typography color="text.secondary">{formatDateRange(startDate, endDate)}</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
              <Box>
                <Typography variant="overline">Symbols</Typography>
                <Typography variant="h5">{symbols.length}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Strategies</Typography>
                <Typography variant="h5">{selectedStrategies.length}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Expanded runs</Typography>
                <Typography variant="h5">{totalRuns}</Typography>
              </Box>
            </Stack>
            {!hasValidDateRange && (
              <Alert severity="warning">End date must be on or after start date.</Alert>
            )}
            <Box>
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={
                  submitting ||
                  loadingStrategies ||
                  !hasValidDateRange ||
                  symbols.length === 0 ||
                  selectedStrategies.length === 0
                }
              >
                {submitting ? 'Submitting…' : 'Launch backtest'}
              </Button>
            </Box>
          </Stack>
        </Paper>
      </Stack>
    </Stack>
  )
}
