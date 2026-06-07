import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Chip,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import type { DailyIndexForecastCreateRequest } from '../types/dailyIndexForecastModels'
import type { RiskModelCreateRequest } from '../types/riskModels'
import type { ReturnForecastModelCreateRequest } from '../types/returnForecastModels'

export type ModelTrainingFamily = 'risk' | 'return_forecast' | 'daily_index_forecast'

export type ModelTrainingLaunchPayload = {
  family: ModelTrainingFamily
  request:
    | RiskModelCreateRequest
    | ReturnForecastModelCreateRequest
    | DailyIndexForecastCreateRequest
}

export type DailyIndexDatasetSource = {
  symbol: string
  start_date: string
  end_date: string
}

interface ModelTrainingLaunchDialogProps {
  open: boolean
  allowedFamilies: ModelTrainingFamily[]
  selectedCount: number
  selectionLabel?: string
  dailyIndexDatasetSource?: DailyIndexDatasetSource | null
  submitting: boolean
  error: string | null
  onClose: () => void
  onSubmit: (payload: ModelTrainingLaunchPayload) => void
}

const STEP_LABELS = ['Choose model', 'Configure', 'Review']

function buildReturnDefaults(): ReturnForecastModelCreateRequest {
  return {
    backtest_ids: [],
    targets: [{ target_key: 'forecast_return', task_type: 'regression' }],
    dataset_config: {},
    train_config: {
      random_seed: 7,
      lookback_bars: 60,
      horizon_bars: 5,
      allow_short: true,
    },
  }
}

function buildDailyIndexDefaults(): DailyIndexForecastCreateRequest {
  return {
    name: null,
    universe: {
      start_date: '2024-01-01',
      end_date: '2024-01-31',
      decision_times: ['09:45'],
      symbols: [{ symbol: 'SPY', data: { type: 'yahoo', symbol: 'SPY' } }],
      benchmark: { symbol: 'QQQ', data: { type: 'yahoo', symbol: 'QQQ' } },
    },
    feature_config: {
      opening_window_minutes: 15,
      rolling_sessions: [5, 20],
      benchmark_sessions: [5, 20],
      use_calendar_features: true,
      use_cross_market_features: true,
    },
    walk_forward: {
      train_days: 90,
      validation_days: 10,
      test_days: 10,
      step_days: 10,
      embargo_days: 1,
      holdout_days: 20,
      min_train_rows: 60,
      min_validation_rows: 10,
      min_test_rows: 10,
      min_holdout_rows: 10,
    },
    train_config: {
      alpha_grid: [0.25, 1, 4, 16],
      residual_distribution: 'normal',
      random_seed: 7,
    },
    costs: {
      spread_bps: 1.5,
      slippage_bps: 1,
      impact_bps: 0.5,
    },
    data_cache: {},
  }
}

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parseNumberList(value: string): number[] {
  return value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item))
}

function familyLabel(family: ModelTrainingFamily): string {
  if (family === 'risk') return 'Risk model'
  if (family === 'return_forecast') return 'Return forecast model'
  return 'Daily index forecast model'
}

function familyDescription(family: ModelTrainingFamily): string {
  if (family === 'risk') return 'Train stop-probability and MAE targets from selected backtests or datasets.'
  if (family === 'return_forecast') return 'Train a short-horizon return forecast from the selected sources.'
  return 'Train the daily index pipeline with the selected dataset provenance.'
}

export function ModelTrainingLaunchDialog({
  open,
  allowedFamilies,
  selectedCount,
  selectionLabel = 'sources',
  dailyIndexDatasetSource,
  submitting,
  error,
  onClose,
  onSubmit,
}: ModelTrainingLaunchDialogProps) {
  const [step, setStep] = useState(0)
  const [family, setFamily] = useState<ModelTrainingFamily>(allowedFamilies[0] ?? 'risk')
  const [name, setName] = useState('')
  const [randomSeed, setRandomSeed] = useState('7')
  const [lookbackBars, setLookbackBars] = useState('60')
  const [horizonBars, setHorizonBars] = useState('5')
  const [allowShort, setAllowShort] = useState(true)
  const [openingWindowMinutes, setOpeningWindowMinutes] = useState('15')
  const [rollingSessions, setRollingSessions] = useState('5,20')
  const [benchmarkSessions, setBenchmarkSessions] = useState('5,20')
  const [useCalendarFeatures, setUseCalendarFeatures] = useState(true)
  const [useCrossMarketFeatures, setUseCrossMarketFeatures] = useState(true)
  const [trainDays, setTrainDays] = useState('90')
  const [validationDays, setValidationDays] = useState('10')
  const [testDays, setTestDays] = useState('10')
  const [stepDays, setStepDays] = useState('10')
  const [embargoDays, setEmbargoDays] = useState('1')
  const [holdoutDays, setHoldoutDays] = useState('20')
  const [minTrainRows, setMinTrainRows] = useState('60')
  const [minValidationRows, setMinValidationRows] = useState('10')
  const [minTestRows, setMinTestRows] = useState('10')
  const [minHoldoutRows, setMinHoldoutRows] = useState('10')
  const [alphaGrid, setAlphaGrid] = useState('0.25,1,4,16')
  const [spreadBps, setSpreadBps] = useState('1.5')
  const [slippageBps, setSlippageBps] = useState('1')
  const [impactBps, setImpactBps] = useState('0.5')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [showRawPayload, setShowRawPayload] = useState(false)

  const availableFamilies = useMemo(() => allowedFamilies, [allowedFamilies])
  const currentFamilyAllowed = availableFamilies.includes(family)

  useEffect(() => {
    if (!open) {
      return
    }
    const initialFamily = allowedFamilies[0] ?? 'risk'
    setStep(0)
    setFamily(initialFamily)
    setName('')
    setValidationError(null)

    const returnDefaults = buildReturnDefaults()
    const dailyDefaults = buildDailyIndexDefaults()
    setRandomSeed(String(returnDefaults.train_config.random_seed))
    setLookbackBars(String(returnDefaults.train_config.lookback_bars))
    setHorizonBars(String(returnDefaults.train_config.horizon_bars))
    setAllowShort(Boolean(returnDefaults.train_config.allow_short))
    setOpeningWindowMinutes(String(dailyDefaults.feature_config.opening_window_minutes))
    setRollingSessions(dailyDefaults.feature_config.rolling_sessions.join(', '))
    setBenchmarkSessions(dailyDefaults.feature_config.benchmark_sessions.join(', '))
    setUseCalendarFeatures(dailyDefaults.feature_config.use_calendar_features)
    setUseCrossMarketFeatures(dailyDefaults.feature_config.use_cross_market_features)
    setTrainDays(String(dailyDefaults.walk_forward.train_days))
    setValidationDays(String(dailyDefaults.walk_forward.validation_days))
    setTestDays(String(dailyDefaults.walk_forward.test_days))
    setStepDays(String(dailyDefaults.walk_forward.step_days))
    setEmbargoDays(String(dailyDefaults.walk_forward.embargo_days))
    setHoldoutDays(String(dailyDefaults.walk_forward.holdout_days))
    setMinTrainRows(String(dailyDefaults.walk_forward.min_train_rows))
    setMinValidationRows(String(dailyDefaults.walk_forward.min_validation_rows))
    setMinTestRows(String(dailyDefaults.walk_forward.min_test_rows))
    setMinHoldoutRows(String(dailyDefaults.walk_forward.min_holdout_rows))
    setAlphaGrid(dailyDefaults.train_config.alpha_grid.join(','))
    setSpreadBps(String(dailyDefaults.costs.spread_bps))
    setSlippageBps(String(dailyDefaults.costs.slippage_bps))
    setImpactBps(String(dailyDefaults.costs.impact_bps))
    setShowRawPayload(false)
  }, [allowedFamilies, open])

  useEffect(() => {
    if (!currentFamilyAllowed && availableFamilies.length > 0) {
      setFamily(availableFamilies[0])
    }
  }, [availableFamilies, currentFamilyAllowed])

  function buildRequest():
    | RiskModelCreateRequest
    | ReturnForecastModelCreateRequest
    | DailyIndexForecastCreateRequest {
    if (family === 'risk') {
      return {
        backtest_ids: [],
        targets: [
          { target_key: 'stop_prob', task_type: 'classification' },
          { target_key: 'mae', task_type: 'regression' },
        ],
        dataset_config: {},
        ...(name.trim() ? { name: name.trim() } : {}),
        train_config: {
          random_seed: parseNumber(randomSeed, 7),
        },
      }
    }

    if (family === 'return_forecast') {
      return {
        ...buildReturnDefaults(),
        ...(name.trim() ? { name: name.trim() } : {}),
        train_config: {
          random_seed: parseNumber(randomSeed, 7),
          lookback_bars: parseNumber(lookbackBars, 60),
          horizon_bars: parseNumber(horizonBars, 5),
          allow_short: allowShort,
        },
      }
    }

    const dailyDefaults = buildDailyIndexDefaults()
    const source = dailyIndexDatasetSource ?? null
    return {
      name: name.trim() ? name.trim() : null,
      universe: {
        start_date: source?.start_date ?? dailyDefaults.universe.start_date,
        end_date: source?.end_date ?? dailyDefaults.universe.end_date,
        decision_times: dailyDefaults.universe.decision_times,
        symbols: [
          {
            symbol: source?.symbol ?? dailyDefaults.universe.symbols[0].symbol ?? 'SPY',
            data: {
              type: 'yahoo',
              symbol: source?.symbol ?? dailyDefaults.universe.symbols[0].symbol ?? 'SPY',
            },
          },
        ],
        benchmark: dailyDefaults.universe.benchmark,
      },
      feature_config: {
        opening_window_minutes: parseNumber(openingWindowMinutes, 15),
        rolling_sessions: parseNumberList(rollingSessions),
        benchmark_sessions: parseNumberList(benchmarkSessions),
        use_calendar_features: useCalendarFeatures,
        use_cross_market_features: useCrossMarketFeatures,
      },
      walk_forward: {
        train_days: parseNumber(trainDays, 90),
        validation_days: parseNumber(validationDays, 10),
        test_days: parseNumber(testDays, 10),
        step_days: parseNumber(stepDays, 10),
        embargo_days: parseNumber(embargoDays, 1),
        holdout_days: parseNumber(holdoutDays, 20),
        min_train_rows: parseNumber(minTrainRows, 60),
        min_validation_rows: parseNumber(minValidationRows, 10),
        min_test_rows: parseNumber(minTestRows, 10),
        min_holdout_rows: parseNumber(minHoldoutRows, 10),
      },
      train_config: {
        alpha_grid: parseNumberList(alphaGrid),
        residual_distribution: 'normal',
        random_seed: parseNumber(randomSeed, 7),
      },
      costs: {
        spread_bps: parseNumber(spreadBps, 1.5),
        slippage_bps: parseNumber(slippageBps, 1),
        impact_bps: parseNumber(impactBps, 0.5),
      },
      data_cache: {},
    }
  }

  function validate(): string | null {
    if (selectedCount === 0) return `Select at least one ${selectionLabel} first.`
    if (family === 'daily_index_forecast') {
      if (selectedCount !== 1 || !dailyIndexDatasetSource) {
        return 'Daily index training from a dataset requires exactly one dataset selection.'
      }
    }
    return null
  }

  function handleNext() {
    if (step === 0) {
      setStep(1)
      return
    }
    if (step === 1) {
      const message = validate()
      setValidationError(message)
      if (!message) {
        setStep(2)
      }
      return
    }
    const message = validate()
    setValidationError(message)
    if (message) return
    onSubmit({
      family,
      request: buildRequest(),
    })
  }

  const title = `Train ${familyLabel(family).toLowerCase()}`
  const helperText =
    step === 0
      ? 'Choose the model family to launch from the selected sources.'
      : step === 1
        ? 'Configure the parameters this model family needs before launch.'
        : 'Review the request before submitting it to Argo.'

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Stack spacing={2.5}>
          <Stepper activeStep={step} alternativeLabel>
            {STEP_LABELS.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
          <Typography color="text.secondary">{helperText}</Typography>
          {error && <Alert severity="error">{error}</Alert>}
          {validationError && <Alert severity="warning">{validationError}</Alert>}

          {step === 0 && (
            <Stack spacing={1.5}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Model family
              </Typography>
              {availableFamilies.map((item) => (
                <ButtonBase
                  key={item}
                  aria-pressed={family === item}
                  aria-label={familyLabel(item)}
                  onClick={() => setFamily(item)}
                  sx={{
                    display: 'block',
                    width: '100%',
                    borderRadius: 1,
                    textAlign: 'left',
                  }}
                >
                  <Box
                    sx={{
                      p: 2,
                      borderRadius: 1,
                      border: 1,
                      borderColor: family === item ? 'primary.main' : 'divider',
                      bgcolor: family === item ? 'action.selected' : 'background.paper',
                      width: '100%',
                      boxShadow: family === item ? 1 : 0,
                      transition: 'transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease',
                      '&:hover': {
                        transform: 'translateY(-1px)',
                        boxShadow: 1,
                        borderColor: 'primary.main',
                      },
                    }}
                  >
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
                      <Typography sx={{ fontWeight: 700 }}>{familyLabel(item)}</Typography>
                      {family === item && <Chip size="small" color="primary" label="Selected" />}
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                      {familyDescription(item)}
                    </Typography>
                  </Box>
                </ButtonBase>
              ))}
            </Stack>
          )}

          {step === 1 && (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    Run details
                  </Typography>
                  <TextField
                    label="Model name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    size="small"
                    helperText="Optional display name for this training run."
                  />
                  <TextField
                    label="Random seed"
                    value={randomSeed}
                    onChange={(e) => setRandomSeed(e.target.value)}
                    size="small"
                    helperText="Keeps fold selection reproducible."
                  />
                </Stack>
              </Paper>
              {family === 'return_forecast' && (
                <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      Return forecast settings
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                      <TextField
                        label="Lookback bars"
                        value={lookbackBars}
                        onChange={(e) => setLookbackBars(e.target.value)}
                        size="small"
                        sx={{ flex: 1 }}
                      />
                      <TextField
                        label="Horizon bars"
                        value={horizonBars}
                        onChange={(e) => setHorizonBars(e.target.value)}
                        size="small"
                        sx={{ flex: 1 }}
                      />
                    </Stack>
                    <FormControlLabel
                      control={<Checkbox checked={allowShort} onChange={(e) => setAllowShort(e.target.checked)} />}
                      label="Allow short signals"
                    />
                  </Stack>
                </Paper>
              )}
              {family === 'daily_index_forecast' && (
                <Stack spacing={2}>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        Dataset provenance
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {dailyIndexDatasetSource
                          ? `Uses dataset provenance: ${dailyIndexDatasetSource.symbol} from ${dailyIndexDatasetSource.start_date} to ${dailyIndexDatasetSource.end_date}.`
                          : 'Select exactly one dataset to inherit its stored symbol and date range.'}
                      </Typography>
                      {!dailyIndexDatasetSource && (
                        <Alert severity="info">
                          Daily index training from a dataset requires one selected dataset.
                        </Alert>
                      )}
                    </Stack>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        Feature config
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Opening window minutes" value={openingWindowMinutes} onChange={(e) => setOpeningWindowMinutes(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Rolling sessions" value={rollingSessions} onChange={(e) => setRollingSessions(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Benchmark sessions" value={benchmarkSessions} onChange={(e) => setBenchmarkSessions(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Alpha grid" value={alphaGrid} onChange={(e) => setAlphaGrid(e.target.value)} size="small" sx={{ flex: 1 }} helperText="Comma-separated numeric values." />
                      </Stack>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <FormControlLabel control={<Checkbox checked={useCalendarFeatures} onChange={(e) => setUseCalendarFeatures(e.target.checked)} />} label="Use calendar features" />
                        <FormControlLabel control={<Checkbox checked={useCrossMarketFeatures} onChange={(e) => setUseCrossMarketFeatures(e.target.checked)} />} label="Use cross-market features" />
                      </Stack>
                    </Stack>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        Walk forward
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Train days" value={trainDays} onChange={(e) => setTrainDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Validation days" value={validationDays} onChange={(e) => setValidationDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Test days" value={testDays} onChange={(e) => setTestDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Step days" value={stepDays} onChange={(e) => setStepDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Embargo days" value={embargoDays} onChange={(e) => setEmbargoDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Holdout days" value={holdoutDays} onChange={(e) => setHoldoutDays(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Min train rows" value={minTrainRows} onChange={(e) => setMinTrainRows(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Min validation rows" value={minValidationRows} onChange={(e) => setMinValidationRows(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Min test rows" value={minTestRows} onChange={(e) => setMinTestRows(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Min holdout rows" value={minHoldoutRows} onChange={(e) => setMinHoldoutRows(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                    </Stack>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        Costs
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        <TextField label="Spread bps" value={spreadBps} onChange={(e) => setSpreadBps(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Slippage bps" value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)} size="small" sx={{ flex: 1 }} />
                        <TextField label="Impact bps" value={impactBps} onChange={(e) => setImpactBps(e.target.value)} size="small" sx={{ flex: 1 }} />
                      </Stack>
                    </Stack>
                  </Paper>
                </Stack>
              )}
            </Stack>
          )}

          {step === 2 && (
            <Stack spacing={1.5}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Review request
              </Typography>
              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                    <Chip label={familyLabel(family)} color="primary" variant="outlined" />
                    <Chip label={`${selectedCount} ${selectionLabel}`} variant="outlined" />
                    <Chip label={name.trim() || 'Unnamed run'} variant="outlined" />
                  </Stack>
                  <Typography color="text.secondary">
                    {family === 'risk' &&
                      'This launch will train stop-probability and MAE targets using the selected sources.'}
                    {family === 'return_forecast' &&
                      'This launch will train a short-horizon return forecast using the selected sources.'}
                    {family === 'daily_index_forecast' &&
                      'This launch will train the daily index pipeline using the selected datasets as provenance.'}
                  </Typography>
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      border: 1,
                      borderColor: 'divider',
                    }}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                      Request summary
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {family === 'risk' && `Seed ${randomSeed}. Targets: stop_prob, mae.`}
                      {family === 'return_forecast' &&
                        `Seed ${randomSeed}. Lookback ${lookbackBars} bars, horizon ${horizonBars} bars, short signals ${allowShort ? 'enabled' : 'disabled'}.`}
                      {family === 'daily_index_forecast' &&
                        (dailyIndexDatasetSource
                          ? `Uses ${dailyIndexDatasetSource.symbol} from ${dailyIndexDatasetSource.start_date} to ${dailyIndexDatasetSource.end_date}.`
                          : 'Select one dataset to use its stored provenance.')}
                    </Typography>
                  </Box>
                  <Button
                    variant="text"
                    onClick={() => setShowRawPayload((current) => !current)}
                    sx={{ width: 'fit-content', px: 0 }}
                  >
                    {showRawPayload ? 'Hide raw payload' : 'Show raw payload'}
                  </Button>
                  {showRawPayload && (
                    <Box
                      sx={{
                        p: 1.5,
                        borderRadius: 1,
                        border: 1,
                        borderColor: 'divider',
                        bgcolor: 'background.paper',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(
                          {
                            ...buildRequest(),
                            ...(family !== 'daily_index_forecast' ? { backtest_ids: undefined, dataset_ids: undefined } : {}),
                          },
                          null,
                          2,
                        )}
                      </Typography>
                    </Box>
                  )}
                </Stack>
              </Paper>
            </Stack>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ gap: 1, justifyContent: 'space-between', px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Stack direction="row" spacing={1}>
          <Button disabled={submitting || step === 0} onClick={() => setStep((current) => Math.max(0, current - 1))}>
            Back
          </Button>
          <Button
            onClick={handleNext}
            variant="contained"
            disabled={submitting || !currentFamilyAllowed}
          >
            {step === 2 ? (submitting ? 'Submitting…' : 'Start training') : 'Next'}
          </Button>
        </Stack>
      </DialogActions>
    </Dialog>
  )
}
