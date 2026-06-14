import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import InfoOutlineRoundedIcon from '@mui/icons-material/InfoOutlineRounded'
import TuneIcon from '@mui/icons-material/Tune'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { createBacktest, fetchBacktestInputConfig } from '../api/backtests'
import { fetchDatasets } from '../api/datasets'
import { fetchRiskModels } from '../api/riskModels'
import { fetchExitRules, fetchStrategies } from '../api/strategies'
import { fetchUniverseConstituents, fetchUniverses } from '../api/universes'
import { BacktestModelPolicyForm } from '../components/BacktestModelPolicyForm'
import { useSettings } from '../settings/useSettings'
import type {
  BacktestFeed,
  BacktestModelPolicyInput,
  BacktestType,
  ClassicBacktestCreateRequest,
  VectorbtBacktestCreateRequest,
} from '../types/backtests'
import type { DatasetListItem } from '../types/datasets'
import type { Resolution } from '../types/marketData'
import type { RiskModelListItem } from '../types/riskModels'
import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'
import type { SymbolUniverse } from '../types/universes'
import { parseInputConfigToPrefill } from '../utils/backtestConfigPrefill'
import { buildOverrideParams, normalizeParamValue } from '../utils/strategyParams'
import { buildStrategyParams, shouldShowCommissionDragWarning } from '../utils/strategyPresets'

const STEPS = ['Type', 'Data', 'Configuration', 'Review']
const RESOLUTIONS: Resolution[] = ['1m', '5m', '15m', '1h', '1d']
const FEEDS: BacktestFeed[] = ['iex', 'sip', 'otc']

type HelpDialogState = {
  title: string
  content: ReactNode
}

function normalizeSymbols(values: string[]): string[] {
  return values
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .filter((item, index, allValues) => allValues.indexOf(item) === index)
}

function sampleSymbols(symbols: string[], sampleSize: number): string[] {
  if (sampleSize <= 0 || symbols.length <= sampleSize) {
    return [...symbols]
  }
  return [...symbols].slice(0, sampleSize)
}

function resolveStartDatePreset(value: '30D' | '90D' | '1Y'): Dayjs {
  if (value === '90D') return dayjs().subtract(90, 'day')
  if (value === '1Y') return dayjs().subtract(1, 'year')
  return dayjs().subtract(30, 'day')
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
  const label = meta.title?.trim() ? meta.title : name
  const helperText = meta.description?.trim() ? meta.description : undefined

  if (Array.isArray(meta.enum) && meta.enum.length > 0) {
    return (
      <FormControl fullWidth size="small">
        <InputLabel id={`${name}-label`}>{label}</InputLabel>
        <Select
          labelId={`${name}-label`}
          label={label}
          value={value ?? meta.enum[0]}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
        >
          {meta.enum.map((option) => (
            <MenuItem key={String(option)} value={option as string | number}>
              {String(option)}
            </MenuItem>
          ))}
        </Select>
        {helperText ? (
          <Typography variant="caption" color="text.secondary" sx={{ pt: 0.5 }}>
            {helperText}
          </Typography>
        ) : null}
      </FormControl>
    )
  }

  if (meta.type === 'boolean') {
    return (
      <TextField
        select
        label={label}
        size="small"
        value={value ? 'true' : 'false'}
        onChange={(event) => onChange(event.target.value === 'true')}
        disabled={disabled}
        helperText={helperText}
        fullWidth
      >
        <MenuItem value="true">True</MenuItem>
        <MenuItem value="false">False</MenuItem>
      </TextField>
    )
  }

  const numeric = meta.type === 'integer' || meta.type === 'number'
  return (
    <TextField
      label={label}
      size="small"
      type={numeric ? 'number' : 'text'}
      value={value ?? ''}
      onChange={(event) => onChange(normalizeParamValue(meta, event.target.value))}
      disabled={disabled}
      helperText={helperText}
      slotProps={{
        htmlInput: {
          min: meta.minimum ?? undefined,
          max: meta.maximum ?? undefined,
          step:
            meta.multipleOf ??
            (meta.type === 'integer' ? 1 : 0.01),
        },
      }}
      fullWidth
    />
  )
}

function TypeCard({
  selected,
  title,
  description,
  onClick,
}: {
  selected: boolean
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <Button
      variant={selected ? 'contained' : 'outlined'}
      color={selected ? 'primary' : 'inherit'}
      onClick={onClick}
      sx={{ justifyContent: 'flex-start', textAlign: 'left', p: 2, height: '100%' }}
      fullWidth
    >
      <Stack spacing={0.5} sx={{ alignItems: 'flex-start' }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Typography variant="body2" color={selected ? 'inherit' : 'text.secondary'}>
          {description}
        </Typography>
      </Stack>
    </Button>
  )
}

function HelpButton({
  title,
  content,
  onOpen,
}: {
  title: string
  content: ReactNode
  onOpen: (state: HelpDialogState) => void
}) {
  return (
    <Tooltip title={`Explain ${title}`}>
      <IconButton
        size="small"
        aria-label={`Explain ${title}`}
        onClick={() => onOpen({ title, content })}
        sx={{ color: 'text.secondary' }}
      >
        <InfoOutlineRoundedIcon fontSize="inherit" />
      </IconButton>
    </Tooltip>
  )
}

function SectionHeader({
  title,
  subtitle,
  helpTitle,
  helpContent,
  onOpenHelp,
  icon,
}: {
  title: string
  subtitle?: string
  helpTitle: string
  helpContent: ReactNode
  onOpenHelp: (state: HelpDialogState) => void
  icon?: ReactNode
}) {
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        {icon}
        <Typography variant="h6">{title}</Typography>
        <HelpButton title={helpTitle} content={helpContent} onOpen={onOpenHelp} />
      </Stack>
      {subtitle ? <Typography variant="body2" color="text.secondary">{subtitle}</Typography> : null}
    </Stack>
  )
}

export function BacktestWizardPage() {
  const { platformSettings } = useSettings()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const errorAlertRef = useRef<HTMLDivElement | null>(null)
  const prefillFromId = searchParams.get('from')
  const downloadPrefillSymbols = searchParams.get('symbols')

  const [step, setStep] = useState(0)
  const [backtestType, setBacktestType] = useState<BacktestType>('classic')
  const [launchMode, setLaunchMode] = useState<'dataset' | 'manual'>('manual')
  const [backtestName, setBacktestName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loadingPrefill, setLoadingPrefill] = useState(Boolean(prefillFromId))
  const [helpDialog, setHelpDialog] = useState<HelpDialogState | null>(null)

  const [availableDatasets, setAvailableDatasets] = useState<DatasetListItem[]>([])
  const [loadingDatasets, setLoadingDatasets] = useState(false)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)

  const [triggers, setTriggers] = useState<StrategyMetadata[]>([])
  const [loadingTriggers, setLoadingTriggers] = useState(true)
  const [exitRules, setExitRules] = useState<StrategyMetadata[]>([])
  const [loadingExitRules, setLoadingExitRules] = useState(true)

  const [availableUniverses, setAvailableUniverses] = useState<SymbolUniverse[]>([])
  const [loadingUniverses, setLoadingUniverses] = useState(false)
  const [selectedUniverseKey, setSelectedUniverseKey] = useState<string | null>(null)
  const [sampleSize, setSampleSize] = useState(20)
  const [samplingUniverse, setSamplingUniverse] = useState(false)

  const [symbols, setSymbols] = useState<string[]>(platformSettings.backtest_defaults.symbols_seed_list)
  const [startDate, setStartDate] = useState<Dayjs | null>(
    resolveStartDatePreset(platformSettings.backtest_defaults.date_range_preset),
  )
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [resolution, setResolution] = useState<Resolution>(platformSettings.backtest_defaults.resolution)
  const [feed, setFeed] = useState<BacktestFeed>(platformSettings.backtest_defaults.feed)
  const [selectedTriggerNames, setSelectedTriggerNames] = useState<string[]>([])
  const [triggerOverrides, setTriggerOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [selectedExitRuleNames, setSelectedExitRuleNames] = useState<string[]>([])
  const [exitRuleOverrides, setExitRuleOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [modelPolicy, setModelPolicy] = useState<BacktestModelPolicyInput | null>(null)
  const [prefillModelPolicy, setPrefillModelPolicy] = useState<BacktestModelPolicyInput | null>(null)

  const [riskModels, setRiskModels] = useState<RiskModelListItem[]>([])
  const [loadingRiskModels, setLoadingRiskModels] = useState(false)
  const [selectedRiskModelId, setSelectedRiskModelId] = useState<string>('')
  const [vectorbtFromDate, setVectorbtFromDate] = useState<Dayjs | null>(null)
  const [vectorbtMaxSymbols, setVectorbtMaxSymbols] = useState<string>('')
  const [volumeWindow, setVolumeWindow] = useState('20')
  const [minVolumeRatio, setMinVolumeRatio] = useState('1.25')
  const [entryCutoffMinutes, setEntryCutoffMinutes] = useState('0')
  const [riskThreshold, setRiskThreshold] = useState('0.5')
  const [exitStyle, setExitStyle] = useState<'vwap' | 'trailing'>('vwap')
  const [minHoldMinutes, setMinHoldMinutes] = useState('0')
  const [atrWindow, setAtrWindow] = useState('14')
  const [atrStopMult, setAtrStopMult] = useState('1.5')

  const selectedDataset = useMemo(
    () => availableDatasets.find((item) => item.id === selectedDatasetId) ?? null,
    [availableDatasets, selectedDatasetId],
  )
  const selectedUniverse = useMemo(
    () => availableUniverses.find((item) => item.key === selectedUniverseKey) ?? null,
    [availableUniverses, selectedUniverseKey],
  )
  const selectedTriggers = useMemo(
    () =>
      selectedTriggerNames
        .map((name) => triggers.find((trigger) => trigger.name === name) ?? null)
        .filter((trigger): trigger is StrategyMetadata => trigger !== null),
    [selectedTriggerNames, triggers],
  )
  const selectedExitRules = useMemo(
    () =>
      selectedExitRuleNames
        .map((name) => exitRules.find((rule) => rule.name === name) ?? null)
        .filter((rule): rule is StrategyMetadata => rule !== null),
    [selectedExitRuleNames, exitRules],
  )
  const totalRuns = launchMode === 'dataset' ? selectedTriggerNames.length : symbols.length * selectedTriggerNames.length
  const hasValidDateRange = startDate !== null && endDate !== null && !endDate.isBefore(startDate, 'day')
  const showCommissionDragWarning = useMemo(
    () =>
      shouldShowCommissionDragWarning(
        resolution,
        platformSettings.backtest_defaults.broker.commission,
        selectedTriggers,
        triggerOverrides,
      ),
    [platformSettings.backtest_defaults.broker.commission, resolution, selectedTriggers, triggerOverrides],
  )

  useLayoutEffect(() => {
    if (!error || !errorAlertRef.current) {
      return
    }
    const element = errorAlertRef.current
    const timer = window.setTimeout(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
      element.focus({ preventScroll: true })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [error])

  useEffect(() => {
    let cancelled = false
    setLoadingDatasets(true)
    void fetchDatasets()
      .then((items) => {
        if (!cancelled) {
          setAvailableDatasets(items.items.filter((item) => item.status === 'completed'))
        }
      })
      .catch(() => {
        if (!cancelled) setAvailableDatasets([])
      })
      .finally(() => {
        if (!cancelled) setLoadingDatasets(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchStrategies()
      .then((items) => {
        if (cancelled) return
        setTriggers(items)
        if (!prefillFromId && items[0]) {
          setSelectedTriggerNames([items[0].name])
          setTriggerOverrides({
            [items[0].name]: buildStrategyParams(items[0], platformSettings.backtest_defaults.resolution),
          })
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load triggers')
      })
      .finally(() => {
        if (!cancelled) setLoadingTriggers(false)
      })
    return () => {
      cancelled = true
    }
  }, [prefillFromId, platformSettings.backtest_defaults.resolution])

  useEffect(() => {
    let cancelled = false
    fetchExitRules()
      .then((items) => {
        if (cancelled) return
        setExitRules(items)
        if (!prefillFromId && items[0]) {
          setSelectedExitRuleNames([items[0].name])
          setExitRuleOverrides({
            [items[0].name]: buildStrategyParams(items[0], platformSettings.backtest_defaults.resolution),
          })
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load exit rules')
      })
      .finally(() => {
        if (!cancelled) setLoadingExitRules(false)
      })
    return () => {
      cancelled = true
    }
  }, [prefillFromId, platformSettings.backtest_defaults.resolution])

  useEffect(() => {
    let cancelled = false
    setLoadingUniverses(true)
    void fetchUniverses(false)
      .then((items) => {
        if (!cancelled) setAvailableUniverses(items)
      })
      .catch((err) => {
        if (!cancelled) {
          setAvailableUniverses([])
          setError(err instanceof Error ? err.message : 'Failed to load universes')
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingUniverses(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoadingRiskModels(true)
    void fetchRiskModels()
      .then((items) => {
        if (!cancelled) {
          setRiskModels(items.filter((item) => item.status === 'succeeded'))
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setRiskModels([])
          setError(err instanceof Error ? err.message : 'Failed to load risk models')
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingRiskModels(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!prefillFromId || loadingTriggers || loadingExitRules || triggers.length === 0 || exitRules.length === 0) {
      return
    }
    let cancelled = false
    setLoadingPrefill(true)
    void fetchBacktestInputConfig(prefillFromId)
      .then((inputConfig) => {
        if (cancelled) return
        const prefill = parseInputConfigToPrefill(inputConfig)
        if (!prefill) throw new Error('Could not parse backtest configuration.')

        const nextTriggerOverrides: Record<string, Record<string, unknown>> = {}
        const nextTriggerNames: string[] = []
        for (const selection of prefill.triggers) {
          const trigger = triggers.find((item) => item.name === selection.name)
          if (!trigger) continue
          nextTriggerNames.push(trigger.name)
          nextTriggerOverrides[trigger.name] = {
            ...buildStrategyParams(trigger, prefill.resolution),
            ...selection.params,
          }
        }

        const nextExitRuleOverrides: Record<string, Record<string, unknown>> = {}
        const nextExitRuleNames: string[] = []
        for (const selection of prefill.exitRules) {
          const rule = exitRules.find((item) => item.name === selection.name)
          if (!rule) continue
          nextExitRuleNames.push(rule.name)
          nextExitRuleOverrides[rule.name] = {
            ...buildStrategyParams(rule, prefill.resolution),
            ...selection.params,
          }
        }

        setBacktestType('classic')
        setLaunchMode('manual')
        setSymbols(prefill.symbols)
        setStartDate(dayjs(prefill.startDate))
        setEndDate(dayjs(prefill.endDate))
        setResolution(prefill.resolution)
        setFeed(prefill.feed)
        setSelectedTriggerNames(nextTriggerNames)
        setTriggerOverrides(nextTriggerOverrides)
        setSelectedExitRuleNames(nextExitRuleNames)
        setExitRuleOverrides(nextExitRuleOverrides)
        setPrefillModelPolicy(prefill.modelPolicy ?? null)
        setModelPolicy(prefill.modelPolicy ?? null)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load backtest configuration')
      })
      .finally(() => {
        if (!cancelled) setLoadingPrefill(false)
      })
    return () => {
      cancelled = true
    }
  }, [prefillFromId, loadingExitRules, loadingTriggers, triggers, exitRules])

  useEffect(() => {
    if (prefillFromId || !downloadPrefillSymbols) {
      return
    }
    const parsedSymbols = normalizeSymbols(downloadPrefillSymbols.split(','))
    if (parsedSymbols.length > 0) {
      setSymbols(parsedSymbols)
    }
  }, [downloadPrefillSymbols, prefillFromId])

  const handleResolutionChange = (nextResolution: Resolution) => {
    setResolution(nextResolution)
    setTriggerOverrides((current) => {
      const next: Record<string, Record<string, unknown>> = {}
      for (const trigger of selectedTriggers) {
        next[trigger.name] = {
          ...buildStrategyParams(trigger, nextResolution),
          ...(current[trigger.name] ?? {}),
        }
      }
      return next
    })
    setExitRuleOverrides((current) => {
      const next: Record<string, Record<string, unknown>> = {}
      for (const rule of selectedExitRules) {
        next[rule.name] = {
          ...buildStrategyParams(rule, nextResolution),
          ...(current[rule.name] ?? {}),
        }
      }
      return next
    })
  }

  const handleTriggerSelectionChange = (nextTriggers: StrategyMetadata[]) => {
    const nextNames = nextTriggers.map((trigger) => trigger.name)
    setSelectedTriggerNames(nextNames)
    setTriggerOverrides((current) => {
      const next: Record<string, Record<string, unknown>> = {}
      for (const trigger of nextTriggers) {
        next[trigger.name] = current[trigger.name] ?? buildStrategyParams(trigger, resolution)
      }
      return next
    })
  }

  const handleExitRuleSelectionChange = (nextRules: StrategyMetadata[]) => {
    const nextNames = nextRules.map((rule) => rule.name)
    setSelectedExitRuleNames(nextNames)
    setExitRuleOverrides((current) => {
      const next: Record<string, Record<string, unknown>> = {}
      for (const rule of nextRules) {
        next[rule.name] = current[rule.name] ?? buildStrategyParams(rule, resolution)
      }
      return next
    })
  }

  const handleSampleFromUniverse = async () => {
    if (!selectedUniverse) {
      setError('Choose a universe before sampling symbols.')
      return
    }
    setSamplingUniverse(true)
    setError(null)
    try {
      const asOf = startDate?.format('YYYY-MM-DD') ?? dayjs().format('YYYY-MM-DD')
      const constituents = await fetchUniverseConstituents(selectedUniverse.key, asOf)
      const nextSymbols = sampleSymbols(normalizeSymbols(constituents.symbols), sampleSize)
      if (nextSymbols.length === 0) {
        throw new Error(`Universe ${selectedUniverse.key} does not have any symbols to sample.`)
      }
      setSymbols(nextSymbols)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sample universe symbols')
    } finally {
      setSamplingUniverse(false)
    }
  }

  const validateCurrentStep = (): string | null => {
    if (step === 1) {
      if (backtestType === 'classic') {
        if (launchMode === 'dataset') {
          if (!selectedDataset) return 'Choose a completed dataset before continuing.'
        } else {
          if (!hasValidDateRange) return 'Choose a valid date range before continuing.'
          if (symbols.length === 0) return 'Add at least one symbol before continuing.'
        }
      } else {
        if (!selectedDataset) return 'Choose a completed dataset for the vector bt run.'
      }
    }
    if (step === 2 && backtestType === 'classic') {
      if (selectedTriggers.length === 0) return 'Choose at least one trigger before continuing.'
      if (selectedExitRules.length === 0) return 'Choose at least one exit rule before continuing.'
    }
    return null
  }

  const handleNext = () => {
    const message = validateCurrentStep()
    setError(message)
    if (message) return
    setStep((current) => Math.min(current + 1, STEPS.length - 1))
  }

  const handleBack = () => setStep((current) => Math.max(current - 1, 0))

  const handleSubmit = async () => {
    const message = validateCurrentStep()
    setError(message)
    if (message) return

    setSubmitting(true)
    setError(null)
    try {
      if (backtestType === 'classic') {
        const payload: ClassicBacktestCreateRequest = {
          backtest_type: 'classic',
          name: backtestName.trim() ? backtestName.trim() : null,
          resolution,
          feed,
          ...(launchMode === 'dataset'
            ? {
                dataset_id: selectedDataset?.id ?? null,
                dataset_path: selectedDataset?.dataset_parquet_path ?? null,
                dataset_manifest_path: selectedDataset?.manifest_path ?? null,
              }
            : {
                start_date: startDate?.format('YYYY-MM-DD'),
                end_date: endDate?.format('YYYY-MM-DD'),
                symbols,
              }),
          triggers: selectedTriggers.map((trigger) => ({
            name: trigger.name,
            params: buildOverrideParams(trigger, triggerOverrides[trigger.name] ?? {}),
          })),
          exit_rules: [
            {
              rules: selectedExitRules.map((rule) => ({
                name: rule.name,
                params: buildOverrideParams(rule, exitRuleOverrides[rule.name] ?? {}),
              })),
            },
          ],
          model_policy: modelPolicy ?? undefined,
        }
        const response = await createBacktest(payload)
        navigate('/backtests', {
          replace: true,
          state: {
            launchResult: {
              status: 'success',
              message: `Backtest ${response.backtest_id} launched successfully.`,
              backtestId: response.backtest_id,
            },
          },
        })
        return
      }

      const payload: VectorbtBacktestCreateRequest = {
        backtest_type: 'vectorbt',
        name: backtestName.trim() ? backtestName.trim() : null,
        dataset_id: selectedDataset?.id ?? null,
        dataset_path: selectedDataset?.dataset_parquet_path ?? null,
        dataset_manifest_path: selectedDataset?.manifest_path ?? null,
        risk_model: selectedRiskModelId.trim() ? { group_id: selectedRiskModelId.trim() } : null,
        from_date: vectorbtFromDate ? vectorbtFromDate.format('YYYY-MM-DD') : undefined,
        max_symbols: vectorbtMaxSymbols.trim() ? Number(vectorbtMaxSymbols) : null,
        volume_window: Number(volumeWindow),
        min_volume_ratio: Number(minVolumeRatio),
        entry_cutoff_minutes: Number(entryCutoffMinutes),
        risk_threshold: Number(riskThreshold),
        exit_style: exitStyle,
        min_hold_minutes: Number(minHoldMinutes),
        atr_window: Number(atrWindow),
        atr_stop_mult: Number(atrStopMult),
      }
      const response = await createBacktest(payload)
      navigate('/backtests', {
        replace: true,
        state: {
          launchResult: {
            status: 'success',
            message: `Backtest ${response.backtest_id} launched successfully.`,
            backtestId: response.backtest_id,
          },
        },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create backtest')
    } finally {
      setSubmitting(false)
    }
  }

  const selectedRiskModel = riskModels.find((item) => item.group_id === selectedRiskModelId) ?? null

  return (
    <Stack spacing={3}>
      <Button component={RouterLink} to="/backtests" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
        Back to results
      </Button>

      <Stack spacing={0.5}>
        <Typography variant="h4">Backtest Wizard</Typography>
        <Typography color="text.secondary">
          Launch either a classic matrix backtest or a focused vector bt workflow from a guided multi-step flow.
        </Typography>
      </Stack>

      {prefillFromId && (
        <Alert severity="info">
          Prefilled from backtest {prefillFromId}. Classic settings can be adjusted before relaunching.
        </Alert>
      )}

      {error && (
        <Box ref={errorAlertRef} tabIndex={-1}>
          <Alert severity="error">{error}</Alert>
        </Box>
      )}

      {loadingPrefill && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <CircularProgress size={20} />
          <Typography color="text.secondary">Loading backtest configuration…</Typography>
        </Stack>
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={3}>
          <Stepper activeStep={step} alternativeLabel>
            {STEPS.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          <Stack spacing={1}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="subtitle2">Run name</Typography>
              <HelpButton
                title="run name"
                onOpen={setHelpDialog}
                content={
                  <Stack spacing={1.5}>
                    <Typography variant="body2">
                      The name is optional metadata for your own organization. It does not change strategy behavior.
                    </Typography>
                    <Typography variant="body2">
                      A good name usually captures the intent of the run, such as the dataset, strategy family, or what changed.
                    </Typography>
                  </Stack>
                }
              />
            </Stack>
            <TextField
              label="Name (optional)"
              value={backtestName}
              onChange={(event) => setBacktestName(event.target.value)}
              helperText="Helps you find this run later."
              slotProps={{ htmlInput: { maxLength: 256 } }}
              fullWidth
            />
          </Stack>

          {step === 0 && (
            <Stack spacing={2}>
              <SectionHeader
                title="Choose a backtest type"
                subtitle="Pick the workflow family first so the wizard can show only the inputs that matter."
                helpTitle="backtest type"
                helpContent={
                  <Stack spacing={1.5}>
                    <Typography variant="body2">
                      Classic backtests use the existing matrix engine. They are best when you want to combine symbols or datasets with trigger and exit-rule variations.
                    </Typography>
                    <Typography variant="body2">
                      Vector bt uses a separate workflow and a curated risk-gated moving-average strategy. It is intentionally narrower, but faster to configure for that use case.
                    </Typography>
                  </Stack>
                }
                onOpenHelp={setHelpDialog}
              />
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                  gap: 2,
                }}
              >
                <TypeCard
                  selected={backtestType === 'classic'}
                  title="Classic backtest"
                  description="Symbol or dataset-backed trigger and exit-rule matrix using the existing backtest engine."
                  onClick={() => setBacktestType('classic')}
                />
                <TypeCard
                  selected={backtestType === 'vectorbt'}
                  title="Vector bt"
                  description="Risk-gated moving-average vector bt workflow with dedicated inputs and a separate Argo template."
                  onClick={() => setBacktestType('vectorbt')}
                />
              </Box>
            </Stack>
          )}

          {step === 1 && backtestType === 'classic' && (
            <Stack spacing={2.5}>
              <SectionHeader
                title="Classic data setup"
                subtitle="Choose whether this run should source bars from a finished dataset or from an ad hoc symbol list and date range."
                helpTitle="classic data setup"
                helpContent={
                  <Stack spacing={1.5}>
                    <Typography variant="body2">
                      Dataset mode reuses a completed dataset artifact. That is the most reproducible choice when you already prepared data upstream.
                    </Typography>
                    <Typography variant="body2">
                      Manual mode is better for exploration. You choose symbols, dates, resolution, and feed directly in the wizard.
                    </Typography>
                    <Typography variant="body2">
                      Sampling from a universe gives you a quick way to seed symbols without typing each ticker by hand.
                    </Typography>
                  </Stack>
                }
                onOpenHelp={setHelpDialog}
              />
              <FormControl fullWidth>
                <InputLabel id="launch-mode-label">Data source</InputLabel>
                <Select
                  labelId="launch-mode-label"
                  label="Data source"
                  value={launchMode}
                  onChange={(event) => setLaunchMode(event.target.value as 'dataset' | 'manual')}
                >
                  <MenuItem value="manual">Manual symbols and date range</MenuItem>
                  <MenuItem value="dataset">Completed dataset</MenuItem>
                </Select>
              </FormControl>

              {launchMode === 'dataset' ? (
                <Autocomplete
                  options={availableDatasets}
                  getOptionLabel={(option) =>
                    `${option.id} — ${option.name ?? option.symbol} (${option.start_date} → ${option.end_date})`
                  }
                  value={selectedDataset}
                  isOptionEqualToValue={(option, value) => option.id === value.id}
                  onChange={(_event, value) => setSelectedDatasetId(value?.id ?? null)}
                  loading={loadingDatasets}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Existing dataset"
                      helperText="Choose a completed dataset for a dataset-backed classic run."
                    />
                  )}
                />
              ) : (
                <>
                  <Autocomplete
                    options={availableUniverses}
                    getOptionLabel={(option) => `${option.name} (${option.key})`}
                    value={selectedUniverse}
                    isOptionEqualToValue={(option, value) => option.key === value.key}
                    onChange={(_event, value) => setSelectedUniverseKey(value?.key ?? null)}
                    loading={loadingUniverses}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Universe"
                        helperText="Optional: sample symbols from a saved universe."
                      />
                    )}
                  />
                  <Stack spacing={1}>
                    <Typography variant="body2">Sample size</Typography>
                    <Slider
                      value={sampleSize}
                      onChange={(_event, nextValue) => setSampleSize(Array.isArray(nextValue) ? nextValue[0] : nextValue)}
                      min={1}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                    />
                    <Button
                      variant="outlined"
                      onClick={() => void handleSampleFromUniverse()}
                      disabled={loadingUniverses || samplingUniverse || selectedUniverse === null}
                      sx={{ alignSelf: 'flex-start' }}
                    >
                      {samplingUniverse ? 'Sampling…' : 'Sample from universe'}
                    </Button>
                  </Stack>
                  <Autocomplete
                    multiple
                    freeSolo
                    options={[]}
                    value={symbols}
                    onChange={(_event, value) => setSymbols(normalizeSymbols(value))}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Symbols"
                        helperText="Type symbols and press Enter to add them."
                      />
                    )}
                  />
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
                  </Stack>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
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
                </>
              )}

              {showCommissionDragWarning && <Alert severity="warning">Intraday defaults can be commission-sensitive for small stake sizes.</Alert>}
            </Stack>
          )}

          {step === 1 && backtestType === 'vectorbt' && (
            <Stack spacing={2.5}>
              <SectionHeader
                title="Vector bt data setup"
                subtitle="Choose the dataset and risk model that define the eligible trading universe and the gating signal."
                helpTitle="vector bt data setup"
                helpContent={
                  <Stack spacing={1.5}>
                    <Typography variant="body2">
                      The completed dataset provides the historical market data. The risk model group is resolved server-side to the concrete artifact used by the workflow.
                    </Typography>
                    <Typography variant="body2">
                      From date lets you trim the backtest start point, and max symbols lets you cap the number of names considered from the dataset.
                    </Typography>
                  </Stack>
                }
                onOpenHelp={setHelpDialog}
              />
              <Autocomplete
                options={availableDatasets}
                getOptionLabel={(option) =>
                  `${option.id} — ${option.name ?? option.symbol} (${option.start_date} → ${option.end_date})`
                }
                value={selectedDataset}
                isOptionEqualToValue={(option, value) => option.id === value.id}
                onChange={(_event, value) => setSelectedDatasetId(value?.id ?? null)}
                loading={loadingDatasets}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Completed dataset"
                    helperText="Vector bt v1 runs against an existing completed dataset parquet."
                  />
                )}
              />
              <Autocomplete
                options={riskModels}
                getOptionLabel={(option) => option.group_id}
                value={selectedRiskModel}
                isOptionEqualToValue={(option, value) => option.group_id === value.group_id}
                onChange={(_event, value) => setSelectedRiskModelId(value?.group_id ?? '')}
                loading={loadingRiskModels}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Risk model group"
                    helperText="Optional. Leave empty to run the vector bt workflow ungated."
                  />
                )}
              />
              {!selectedRiskModelId.trim() && (
                <Alert severity="info">
                  No risk model selected. This run will be submitted as an ungated vector bt backtest.
                </Alert>
              )}
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <DatePicker
                  label="From date (optional)"
                  value={vectorbtFromDate}
                  onChange={setVectorbtFromDate}
                  slotProps={{ textField: { fullWidth: true } }}
                />
                <TextField
                  label="Max symbols (optional)"
                  type="number"
                  value={vectorbtMaxSymbols}
                  onChange={(event) => setVectorbtMaxSymbols(event.target.value)}
                  helperText="Limit tradable symbols from the dataset."
                  slotProps={{ htmlInput: { min: 1, step: 1 } }}
                  fullWidth
                />
              </Stack>
            </Stack>
          )}

          {step === 2 && backtestType === 'classic' && (
            <Stack spacing={3}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={2}>
                  <SectionHeader
                    title="Triggers"
                    subtitle="Select the entry strategies to expand across your chosen symbols or dataset."
                    helpTitle="triggers"
                    helpContent={
                      <Stack spacing={1.5}>
                        <Typography variant="body2">
                          Each trigger defines how a run enters positions. Selecting multiple triggers expands the classic run matrix.
                        </Typography>
                        <Typography variant="body2">
                          Parameter overrides let you tune each trigger without editing raw YAML. The review step will reflect the final combination count.
                        </Typography>
                      </Stack>
                    }
                    onOpenHelp={setHelpDialog}
                    icon={<TuneIcon color="primary" />}
                  />
                  {loadingTriggers ? (
                    <CircularProgress size={20} />
                  ) : (
                    <>
                      <Autocomplete
                        multiple
                        options={triggers}
                        getOptionLabel={(option) => option.name}
                        value={selectedTriggers}
                        onChange={(_event, value) => handleTriggerSelectionChange(value)}
                        renderInput={(params) => <TextField {...params} label="Triggers" helperText="Choose one or more triggers." />}
                      />
                      {selectedTriggers.map((strategy) => {
                        const params = triggerOverrides[strategy.name] ?? buildStrategyParams(strategy, resolution)
                        return (
                          <Paper key={strategy.name} variant="outlined" sx={{ p: 2 }}>
                            <Stack spacing={1.5}>
                              <Typography variant="subtitle1">{strategy.name}</Typography>
                              <Typography variant="body2" color="text.secondary">
                                {strategy.description}
                              </Typography>
                              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
                                {Object.entries(strategy.parameters).map(([name, meta]) => (
                                  <ParameterField
                                    key={`${strategy.name}-${name}`}
                                    name={name}
                                    meta={meta}
                                    value={params[name]}
                                    disabled={submitting}
                                    onChange={(value) =>
                                      setTriggerOverrides((current) => ({
                                        ...current,
                                        [strategy.name]: { ...(current[strategy.name] ?? {}), [name]: value },
                                      }))
                                    }
                                  />
                                ))}
                              </Box>
                            </Stack>
                          </Paper>
                        )
                      })}
                    </>
                  )}
                </Stack>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={2}>
                  <SectionHeader
                    title="Exit rules"
                    subtitle="Choose how positions are closed and in what order those exit checks run."
                    helpTitle="exit rules"
                    helpContent={
                      <Stack spacing={1.5}>
                        <Typography variant="body2">
                          Exit rules are evaluated in order. You can combine complementary rules such as protective stops and maximum hold limits.
                        </Typography>
                        <Typography variant="body2">
                          Like triggers, choosing multiple exit-rule definitions expands the classic backtest matrix.
                        </Typography>
                      </Stack>
                    }
                    onOpenHelp={setHelpDialog}
                    icon={<TuneIcon color="primary" />}
                  />
                  {loadingExitRules ? (
                    <CircularProgress size={20} />
                  ) : (
                    <>
                      <Autocomplete
                        multiple
                        options={exitRules}
                        getOptionLabel={(option) => option.name}
                        value={selectedExitRules}
                        onChange={(_event, value) => handleExitRuleSelectionChange(value)}
                        renderInput={(params) => <TextField {...params} label="Exit rules" helperText="Choose ordered exit rules." />}
                      />
                      {selectedExitRules.map((rule) => {
                        const params = exitRuleOverrides[rule.name] ?? buildStrategyParams(rule, resolution)
                        return (
                          <Paper key={rule.name} variant="outlined" sx={{ p: 2 }}>
                            <Stack spacing={1.5}>
                              <Typography variant="subtitle1">{rule.name}</Typography>
                              <Typography variant="body2" color="text.secondary">
                                {rule.description}
                              </Typography>
                              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
                                {Object.entries(rule.parameters).map(([name, meta]) => (
                                  <ParameterField
                                    key={`${rule.name}-${name}`}
                                    name={name}
                                    meta={meta}
                                    value={params[name]}
                                    disabled={submitting}
                                    onChange={(value) =>
                                      setExitRuleOverrides((current) => ({
                                        ...current,
                                        [rule.name]: { ...(current[rule.name] ?? {}), [name]: value },
                                      }))
                                    }
                                  />
                                ))}
                              </Box>
                            </Stack>
                          </Paper>
                        )
                      })}
                    </>
                  )}
                </Stack>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={2}>
                  <SectionHeader
                    title="Model policy"
                    subtitle="Optionally layer forecast and risk models onto the classic strategy flow."
                    helpTitle="model policy"
                    helpContent={
                      <Stack spacing={1.5}>
                        <Typography variant="body2">
                          Model policy is optional. Use it when you want model outputs to gate or size trades on top of the trigger logic.
                        </Typography>
                        <Typography variant="body2">
                          The form follows the existing model-selection patterns, so you reference model groups and let the backend resolve the correct artifacts.
                        </Typography>
                      </Stack>
                    }
                    onOpenHelp={setHelpDialog}
                  />
                  <BacktestModelPolicyForm
                    disabled={submitting}
                    initialValue={prefillModelPolicy}
                    onChange={setModelPolicy}
                  />
                </Stack>
              </Paper>
            </Stack>
          )}

          {step === 2 && backtestType === 'vectorbt' && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={2}>
                <SectionHeader
                  title="Vector bt configuration"
                  subtitle="Tune the curated risk-gated moving-average strategy from the reference script."
                  helpTitle="vector bt configuration"
                  helpContent={
                    <Stack spacing={1.5}>
                      <Typography variant="body2">
                        Volume window and minimum volume ratio control liquidity filtering. Entry cutoff minutes prevents fresh entries too late in the session.
                      </Typography>
                      <Typography variant="body2">
                        Risk threshold decides how strict the model gate is. Exit style switches between a VWAP-oriented exit and a trailing ATR-style approach.
                      </Typography>
                      <Typography variant="body2">
                        Min hold minutes, ATR window, and ATR stop multiplier shape how quickly trades can exit and how wide the trailing stop logic is.
                      </Typography>
                    </Stack>
                  }
                  onOpenHelp={setHelpDialog}
                />
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField label="Volume window" type="number" value={volumeWindow} onChange={(event) => setVolumeWindow(event.target.value)} fullWidth />
                  <TextField label="Min volume ratio" type="number" value={minVolumeRatio} onChange={(event) => setMinVolumeRatio(event.target.value)} fullWidth />
                </Stack>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField label="Entry cutoff minutes" type="number" value={entryCutoffMinutes} onChange={(event) => setEntryCutoffMinutes(event.target.value)} fullWidth />
                  <TextField
                    label="Risk threshold"
                    type="number"
                    value={riskThreshold}
                    onChange={(event) => setRiskThreshold(event.target.value)}
                    helperText={selectedRiskModelId.trim() ? 'Entries at or above this score are blocked.' : 'Ignored for ungated runs.'}
                    disabled={!selectedRiskModelId.trim()}
                    fullWidth
                  />
                </Stack>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel id="exit-style-label">Exit style</InputLabel>
                    <Select labelId="exit-style-label" label="Exit style" value={exitStyle} onChange={(event) => setExitStyle(event.target.value as 'vwap' | 'trailing')}>
                      <MenuItem value="vwap">VWAP</MenuItem>
                      <MenuItem value="trailing">Trailing</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField label="Min hold minutes" type="number" value={minHoldMinutes} onChange={(event) => setMinHoldMinutes(event.target.value)} fullWidth />
                </Stack>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField label="ATR window" type="number" value={atrWindow} onChange={(event) => setAtrWindow(event.target.value)} fullWidth />
                  <TextField label="ATR stop multiplier" type="number" value={atrStopMult} onChange={(event) => setAtrStopMult(event.target.value)} fullWidth />
                </Stack>
              </Stack>
            </Paper>
          )}

          {step === 3 && (
            <Stack spacing={2}>
              <SectionHeader
                title="Review"
                subtitle="Double-check the launch payload before creating the workflow."
                helpTitle="review"
                helpContent={
                  <Stack spacing={1.5}>
                    <Typography variant="body2">
                      The review step is the last checkpoint before the job is submitted. Use it to confirm the job family, data source, and the key strategy choices.
                    </Typography>
                    <Typography variant="body2">
                      For classic runs, the estimated run count reflects matrix expansion across symbols, triggers, and exit rules. For vector bt, the summary focuses on the curated workflow inputs.
                    </Typography>
                  </Stack>
                }
                onOpenHelp={setHelpDialog}
              />
              {backtestType === 'classic' ? (
                <Stack spacing={1}>
                  <Typography>Type: Classic backtest</Typography>
                  <Typography>Data source: {launchMode === 'dataset' ? selectedDataset?.id ?? 'None selected' : `${symbols.length} symbols`}</Typography>
                  <Typography>Triggers: {selectedTriggerNames.join(', ') || 'None selected'}</Typography>
                  <Typography>Exit rules: {selectedExitRuleNames.join(', ') || 'None selected'}</Typography>
                  <Typography>Estimated runs: {totalRuns}</Typography>
                </Stack>
              ) : (
                <Stack spacing={1}>
                  <Typography>Type: Vector bt</Typography>
                  <Typography>Dataset: {selectedDataset?.id ?? 'None selected'}</Typography>
                  <Typography>Risk model: {selectedRiskModelId || 'Ungated'}</Typography>
                  <Typography>Exit style: {exitStyle}</Typography>
                  <Typography>Risk threshold: {selectedRiskModelId ? riskThreshold : 'Not used'}</Typography>
                </Stack>
              )}
            </Stack>
          )}

          <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between' }}>
            <Button onClick={handleBack} disabled={step === 0 || submitting}>
              Back
            </Button>
            <Stack direction="row" spacing={1}>
              {step < STEPS.length - 1 ? (
                <Button variant="contained" onClick={handleNext} disabled={submitting}>
                  Continue
                </Button>
              ) : (
                <Button variant="contained" onClick={() => void handleSubmit()} disabled={submitting}>
                  {submitting ? 'Launching…' : 'Launch backtest'}
                </Button>
              )}
            </Stack>
          </Stack>
        </Stack>
      </Paper>

      {selectedTriggerNames.length > 0 && backtestType === 'classic' && (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          {selectedTriggerNames.map((name) => (
            <Chip key={name} label={name} size="small" color="primary" variant="outlined" />
          ))}
        </Stack>
      )}

      <Dialog open={helpDialog !== null} onClose={() => setHelpDialog(null)} fullWidth maxWidth="sm">
        <DialogTitle>{helpDialog?.title}</DialogTitle>
        <DialogContent dividers>{helpDialog?.content}</DialogContent>
      </Dialog>
    </Stack>
  )
}
