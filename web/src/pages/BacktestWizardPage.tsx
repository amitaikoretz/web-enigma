import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import TuneIcon from '@mui/icons-material/Tune'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  Link,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  Switch,
  Tooltip,
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { createBacktest, fetchBacktestInputConfig } from '../api/backtests'
import { fetchDatasets } from '../api/datasets'
import { fetchUniverses, fetchUniverseConstituents } from '../api/universes'
import { BacktestModelPolicyForm } from '../components/BacktestModelPolicyForm'
import { fetchExitRules, fetchStrategies } from '../api/strategies'
import { useSettings } from '../settings/useSettings'
import type { BacktestFeed, BacktestModelPolicyInput } from '../types/backtests'
import type { Resolution } from '../types/marketData'
import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'
import type { DatasetListItem } from '../types/datasets'
import type { SymbolUniverse } from '../types/universes'
import {
  buildOverrideParams,
  normalizeParamValue,
} from '../utils/strategyParams'
import { parseInputConfigToPrefill } from '../utils/backtestConfigPrefill'
import {
  buildStrategyParams,
  shouldShowCommissionDragWarning,
} from '../utils/strategyPresets'

const RESOLUTIONS: Resolution[] = ['1m', '5m', '15m', '1h', '1d']
const FEEDS: BacktestFeed[] = ['iex', 'sip', 'otc']

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

  const shuffled = [...symbols]
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    ;[shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]]
  }
  return shuffled.slice(0, sampleSize)
}

function resolveStartDatePreset(value: '30D' | '90D' | '1Y'): Dayjs {
  if (value === '90D') return dayjs().subtract(90, 'day')
  if (value === '1Y') return dayjs().subtract(1, 'year')
  return dayjs().subtract(30, 'day')
}

function formatReviewDateRange(startDate: Dayjs | null, endDate: Dayjs | null): string {
  if (!startDate || !endDate) {
    return 'Choose a start and end date.'
  }
  return `${startDate.format('MMM D, YYYY')} → ${endDate.format('MMM D, YYYY')}`
}

interface LaunchResultState {
  status: 'success' | 'failed'
  message: string
  backtestId?: string
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
            <MenuItem key={String(option)} value={option as any}>
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
      <Stack spacing={0.25}>
        <FormControlLabel
          control={
            <Switch
              checked={Boolean(value)}
              onChange={(_event, checked) => onChange(checked)}
              disabled={disabled}
            />
          }
          label={label}
        />
        {helperText ? (
          <Typography variant="caption" color="text.secondary">
            {helperText}
          </Typography>
        ) : null}
      </Stack>
    )
  }

  const numeric = meta.type === 'integer' || meta.type === 'number'
  const min = meta.minimum ?? undefined
  const max = meta.maximum ?? undefined
  const range = typeof min === 'number' && typeof max === 'number' ? max - min : undefined
  const step =
    typeof meta.multipleOf === 'number'
      ? meta.multipleOf
      : meta.type === 'integer'
        ? 1
        : typeof range === 'number' && range <= 1
          ? 0.001
          : 0.01

  const isPct =
    numeric &&
    (name.endsWith('_pct') ||
      (typeof min === 'number' && typeof max === 'number' && min >= 0 && max <= 1 && max - min <= 1))

  const shouldUseSlider = numeric && typeof min === 'number' && typeof max === 'number' && max > min && max - min <= 200

  if (shouldUseSlider) {
    const numericValue =
      typeof value === 'number' && Number.isFinite(value) ? value : (meta.default as number | undefined) ?? min ?? 0

    return (
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="body2" sx={{ flex: 1 }}>
            {label}
          </Typography>
          <TextField
            size="small"
            type="number"
            value={numericValue}
            onChange={(event) => onChange(normalizeParamValue(meta, event.target.value))}
            disabled={disabled}
            slotProps={{
              htmlInput: {
                min,
                max,
                step,
              },
            }}
            sx={{ width: 140 }}
          />
        </Stack>
        <Slider
          value={numericValue}
          onChange={(_event, newValue) => onChange(newValue as number)}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          valueLabelDisplay="auto"
          valueLabelFormat={(v) => (isPct ? `${Math.round(v * 10000) / 100}%` : String(v))}
        />
        {helperText ? (
          <Typography variant="caption" color="text.secondary">
            {helperText}
          </Typography>
        ) : null}
      </Stack>
    )
  }

  return (
    <TextField
      label={label}
      size="small"
      type={meta.type === 'string' ? 'text' : 'number'}
      value={value ?? ''}
      onChange={(event) => onChange(normalizeParamValue(meta, event.target.value))}
      disabled={disabled}
      helperText={helperText}
      slotProps={{
        htmlInput: {
          min,
          max,
          step: numeric ? step : undefined,
        },
      }}
      fullWidth
    />
  )
}

export function BacktestWizardPage() {
  const { platformSettings } = useSettings()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const errorAlertRef = useRef<HTMLDivElement | null>(null)
  const prefillFromId = searchParams.get('from')
  const downloadPrefillSymbols = searchParams.get('symbols')
  const [triggers, setTriggers] = useState<StrategyMetadata[]>([])
  const [loadingTriggers, setLoadingTriggers] = useState(true)
  const [exitRules, setExitRules] = useState<StrategyMetadata[]>([])
  const [loadingExitRules, setLoadingExitRules] = useState(true)
  const [loadingPrefill, setLoadingPrefill] = useState(Boolean(prefillFromId))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [launchResult, setLaunchResult] = useState<LaunchResultState | null>(null)
  const [backtestName, setBacktestName] = useState('')
  const [prefillSourceId, setPrefillSourceId] = useState<string | null>(null)
  const [launchMode, setLaunchMode] = useState<'dataset' | 'legacy'>('legacy')
  const [symbols, setSymbols] = useState<string[]>(platformSettings.backtest_defaults.symbols_seed_list)
  const [startDate, setStartDate] = useState<Dayjs | null>(
    resolveStartDatePreset(platformSettings.backtest_defaults.date_range_preset),
  )
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [resolution, setResolution] = useState<Resolution>(platformSettings.backtest_defaults.resolution)
  const [feed, setFeed] = useState<BacktestFeed>(platformSettings.backtest_defaults.feed)
  const [availableDatasets, setAvailableDatasets] = useState<DatasetListItem[]>([])
  const [loadingDatasets, setLoadingDatasets] = useState(false)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const [availableUniverses, setAvailableUniverses] = useState<SymbolUniverse[]>([])
  const [loadingUniverses, setLoadingUniverses] = useState(false)
  const [selectedUniverseKey, setSelectedUniverseKey] = useState<string | null>(null)
  const [sampleSize, setSampleSize] = useState(20)
  const [samplingUniverse, setSamplingUniverse] = useState(false)
  const [selectedTriggerNames, setSelectedTriggerNames] = useState<string[]>([])
  const [triggerOverrides, setTriggerOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [selectedExitRuleNames, setSelectedExitRuleNames] = useState<string[]>([])
  const [exitRuleOverrides, setExitRuleOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [modelPolicy, setModelPolicy] = useState<BacktestModelPolicyInput | null>(null)
  const [prefillModelPolicy, setPrefillModelPolicy] = useState<BacktestModelPolicyInput | null>(null)
  const [pendingExitRuleToAdd, setPendingExitRuleToAdd] = useState<StrategyMetadata | null>(null)
  const [documentationStrategy, setDocumentationStrategy] = useState<StrategyMetadata | null>(null)
  const [submitBroker, setSubmitBroker] = useState(platformSettings.backtest_defaults.broker)
  const [submitAnalyzers, setSubmitAnalyzers] = useState(platformSettings.backtest_defaults.analyzers)
  const [submitExecution, setSubmitExecution] = useState(platformSettings.backtest_defaults.execution)
  const selectedDataset = useMemo(
    () => availableDatasets.find((item) => item.id === selectedDatasetId) ?? null,
    [availableDatasets, selectedDatasetId],
  )
  const selectedUniverse = useMemo(
    () => availableUniverses.find((item) => item.key === selectedUniverseKey) ?? null,
    [availableUniverses, selectedUniverseKey],
  )

  useEffect(() => {
    if (selectedUniverseKey === null && availableUniverses.length === 1) {
      setSelectedUniverseKey(availableUniverses[0].key)
    }
  }, [availableUniverses, selectedUniverseKey])

  const totalRuns = launchMode === 'dataset' ? selectedTriggerNames.length : symbols.length * selectedTriggerNames.length

  useEffect(() => {
    if (prefillFromId || !downloadPrefillSymbols) {
      return undefined
    }

    const parsedSymbols = downloadPrefillSymbols
      .split(',')
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean)
      .filter((item, index, values) => values.indexOf(item) === index)
    if (parsedSymbols.length === 0) {
      return undefined
    }

    const nextResolution = searchParams.get('resolution')
    const nextFeed = searchParams.get('feed')

    if (nextResolution && RESOLUTIONS.includes(nextResolution as Resolution)) {
      setResolution(nextResolution as Resolution)
    }
    if (nextFeed && FEEDS.includes(nextFeed as BacktestFeed)) {
      setFeed(nextFeed as BacktestFeed)
    }

    return undefined
  }, [downloadPrefillSymbols, prefillFromId, searchParams])

  useEffect(() => {
    let cancelled = false
    fetchStrategies()
      .then((items) => {
        if (cancelled) {
          return
        }
        setTriggers(items)
        if (!prefillFromId && items[0]) {
          setSelectedTriggerNames([items[0].name])
          setTriggerOverrides({
            [items[0].name]: buildStrategyParams(items[0], platformSettings.backtest_defaults.resolution),
          })
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load triggers')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingTriggers(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [prefillFromId, platformSettings.backtest_defaults.resolution])

  useEffect(() => {
    let cancelled = false
    fetchExitRules()
      .then((items) => {
        if (cancelled) {
          return
        }
        setExitRules(items)
        if (!prefillFromId && items[0]) {
          setSelectedExitRuleNames([items[0].name])
          setExitRuleOverrides({
            [items[0].name]: buildStrategyParams(items[0], platformSettings.backtest_defaults.resolution),
          })
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load exit rules')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingExitRules(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [prefillFromId, platformSettings.backtest_defaults.resolution])

  useEffect(() => {
    let cancelled = false
    setLoadingDatasets(true)
    void fetchDatasets()
      .then((items) => {
        if (cancelled) {
          return
        }
        setAvailableDatasets(items.items.filter((item) => item.status === 'completed'))
      })
      .catch(() => {
        if (!cancelled) {
          setAvailableDatasets([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingDatasets(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoadingUniverses(true)
    void fetchUniverses(false)
      .then((items) => {
        if (cancelled) {
          return
        }
        setAvailableUniverses(items)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load universes')
          setAvailableUniverses([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingUniverses(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!prefillFromId || loadingTriggers || loadingExitRules || triggers.length === 0 || exitRules.length === 0) {
      return undefined
    }

    let cancelled = false
    setLoadingPrefill(true)
    setError(null)

    void fetchBacktestInputConfig(prefillFromId)
      .then((inputConfig) => {
        if (cancelled) {
          return
        }

        const prefill = parseInputConfigToPrefill(inputConfig)
        if (!prefill) {
          throw new Error('Could not parse backtest configuration.')
        }

        const nextTriggerOverrides: Record<string, Record<string, unknown>> = {}
        const nextTriggerNames: string[] = []
        for (const selection of prefill.triggers) {
          const trigger = triggers.find((item) => item.name === selection.name)
          if (!trigger) {
            continue
          }
          nextTriggerNames.push(trigger.name)
          nextTriggerOverrides[trigger.name] = {
            ...buildStrategyParams(trigger, prefill.resolution),
            ...selection.params,
          }
        }

        if (nextTriggerNames.length === 0) {
          throw new Error('None of the original triggers are available on this server.')
        }

        const nextExitRuleOverrides: Record<string, Record<string, unknown>> = {}
        const nextExitRuleNames: string[] = []
        for (const selection of prefill.exitRules) {
          const rule = exitRules.find((item) => item.name === selection.name)
          if (!rule) {
            continue
          }
          nextExitRuleNames.push(rule.name)
          nextExitRuleOverrides[rule.name] = {
            ...buildStrategyParams(rule, prefill.resolution),
            ...selection.params,
          }
        }

        if (nextExitRuleNames.length === 0) {
          throw new Error('None of the original exit rules are available on this server.')
        }

        setLaunchMode('legacy')
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
        setSubmitBroker(prefill.broker ?? platformSettings.backtest_defaults.broker)
        setSubmitAnalyzers(prefill.analyzers ?? platformSettings.backtest_defaults.analyzers)
        setSubmitExecution(prefill.execution ?? platformSettings.backtest_defaults.execution)
        setPrefillSourceId(prefillFromId)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load backtest configuration')
          setPrefillSourceId(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPrefill(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [prefillFromId, loadingExitRules, loadingTriggers, triggers, exitRules, platformSettings.backtest_defaults])

  const selectedTriggers = useMemo(
    () =>
      selectedTriggerNames
        .map((name) => triggers.find((trigger) => trigger.name === name) ?? null)
        .filter((trigger): trigger is StrategyMetadata => trigger !== null),
    [selectedTriggerNames, triggers],
  )

  const formatDefaultValue = (value: unknown): string => {
    if (value === null || value === undefined) {
      return '—'
    }
    if (typeof value === 'string') {
      return value
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value)
    }
    return JSON.stringify(value)
  }

  const selectedExitRules = useMemo(
    () =>
      selectedExitRuleNames
        .map((name) => exitRules.find((rule) => rule.name === name) ?? null)
        .filter((rule): rule is StrategyMetadata => rule !== null),
    [selectedExitRuleNames, exitRules],
  )

  const hasValidDateRange = startDate !== null && endDate !== null && !endDate.isBefore(startDate, 'day')

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

  const showCommissionDragWarning = useMemo(
    () =>
      shouldShowCommissionDragWarning(
        resolution,
        submitBroker.commission,
        selectedTriggers,
        triggerOverrides,
      ),
    [resolution, submitBroker.commission, selectedTriggers, triggerOverrides],
  )

  const handleTriggerSelectionChange = (nextTriggers: StrategyMetadata[]) => {
    const nextNames = nextTriggers.map((trigger) => trigger.name)
    setSelectedTriggerNames(nextNames)
    setTriggerOverrides((current) => {
      const nextOverrides: Record<string, Record<string, unknown>> = {}
      for (const trigger of nextTriggers) {
        nextOverrides[trigger.name] =
          current[trigger.name] ?? buildStrategyParams(trigger, resolution)
      }
      return nextOverrides
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

  const handleResolutionChange = (nextResolution: Resolution) => {
    setResolution(nextResolution)
    setTriggerOverrides(() => {
      const nextOverrides: Record<string, Record<string, unknown>> = {}
      for (const trigger of selectedTriggers) {
        nextOverrides[trigger.name] = buildStrategyParams(trigger, nextResolution)
      }
      return nextOverrides
    })
    setExitRuleOverrides(() => {
      const nextOverrides: Record<string, Record<string, unknown>> = {}
      for (const ruleName of selectedExitRuleNames) {
        const rule = exitRules.find((item) => item.name === ruleName) ?? null
        nextOverrides[ruleName] = buildStrategyParams(rule, nextResolution)
      }
      return nextOverrides
    })
  }


  const handleTriggerParamChange = (triggerName: string, name: string, value: unknown) => {
    setTriggerOverrides((current) => ({
      ...current,
      [triggerName]: {
        ...(current[triggerName] ?? {}),
        [name]: value,
      },
    }))
  }

  const handleExitRuleParamChange = (ruleName: string, name: string, value: unknown) => {
    setExitRuleOverrides((current) => ({
      ...current,
      [ruleName]: {
        ...(current[ruleName] ?? {}),
        [name]: value,
      },
    }))
  }

  const availableExitRulesToAdd = useMemo(
    () => exitRules.filter((rule) => !selectedExitRuleNames.includes(rule.name)),
    [exitRules, selectedExitRuleNames],
  )

  const addExitRule = (rule: StrategyMetadata | null) => {
    if (!rule) {
      return
    }
    setSelectedExitRuleNames((current) => (current.includes(rule.name) ? current : [...current, rule.name]))
    setExitRuleOverrides((current) => ({
      ...current,
      [rule.name]: current[rule.name] ?? buildStrategyParams(rule, resolution),
    }))
    setPendingExitRuleToAdd(null)
  }

  const removeExitRule = (ruleName: string) => {
    setSelectedExitRuleNames((current) => current.filter((name) => name !== ruleName))
    setExitRuleOverrides((current) => {
      const next = { ...current }
      delete next[ruleName]
      return next
    })
  }

  const moveExitRule = (ruleName: string, direction: -1 | 1) => {
    setSelectedExitRuleNames((current) => {
      const index = current.indexOf(ruleName)
      if (index < 0) {
        return current
      }
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= current.length) {
        return current
      }
      const next = [...current]
      const [item] = next.splice(index, 1)
      next.splice(nextIndex, 0, item)
      return next
    })
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLaunchResult(null)
    if (launchMode === 'dataset') {
      if (!selectedDataset || !selectedDataset.dataset_parquet_path || !selectedDataset.manifest_path) {
        setError('Choose a completed dataset before submitting.')
        return
      }
    } else if (!hasValidDateRange) {
      setError('Choose a valid date range before submitting.')
      return
    }
    if (selectedTriggers.length === 0 || selectedExitRuleNames.length === 0) {
      setError('Add at least one trigger and exit rule before submitting.')
      return
    }

    if (platformSettings.platform_behavior.confirm_before_launch) {
      const confirmed =
        launchMode === 'dataset'
          ? window.confirm(
              `Launch ${totalRuns} backtest run${totalRuns === 1 ? '' : 's'} from dataset ${selectedDataset?.id}?`,
            )
          : window.confirm(
              `Launch ${totalRuns} backtest run${totalRuns === 1 ? '' : 's'} using ${symbols.length} symbol${symbols.length === 1 ? '' : 's'}?`,
            )
      if (!confirmed) {
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      const response = await createBacktest({
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
        broker: submitBroker,
        analyzers: submitAnalyzers,
        execution: submitExecution,
      })
      const nextLaunchResult = {
        status: 'success',
        message: `Backtest ${response.backtest_id} launched successfully.`,
        backtestId: response.backtest_id,
      } as const
      setLaunchResult(nextLaunchResult)
      navigate('/backtests', {
        replace: true,
        state: { launchResult: nextLaunchResult },
      })
    } catch (err) {
      setLaunchResult({
        status: 'failed',
        message: err instanceof Error ? err.message : 'Failed to create backtest',
      })
    } finally {
      setSubmitting(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  return (
    <Stack spacing={3}>
      <Button component={RouterLink} to="/backtests" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
        Back to results
      </Button>

      <Stack spacing={0.5}>
        <Typography variant="h4">Backtest Wizard</Typography>
        <Typography color="text.secondary">
          Select an existing dataset, then choose triggers and exit rules for the backtest matrix.
        </Typography>
      </Stack>

      {prefillSourceId && (
        <Alert severity="info">
          Prefilled from backtest `{prefillSourceId}`. Edit any settings below before launching.
        </Alert>
      )}

      {!prefillSourceId && downloadPrefillSymbols && (
        <Alert severity="info">
          Prefilled from a market data download job. Choose a completed dataset, then choose triggers and exit rules below before launching.
        </Alert>
      )}

      <Dialog
        open={launchResult !== null}
        onClose={() => setLaunchResult(null)}
        aria-labelledby="launch-result-title"
        aria-describedby="launch-result-description"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(6px)',
              backgroundColor: 'rgba(0, 0, 0, 0.55)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              maxWidth: 520,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="launch-result-title" sx={{ pb: 1 }}>
          {launchResult?.status === 'success' ? 'Backtest launched' : 'Backtest launch failed'}
        </DialogTitle>
        <DialogContent id="launch-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={launchResult?.status === 'success' ? 'success' : 'error'}>
              {launchResult?.message}
            </Alert>
            {launchResult?.status === 'success' && launchResult.backtestId && (
              <Typography color="text.secondary">
                You can open the new job from{' '}
                <Link component={RouterLink} to={`/backtests/${launchResult.backtestId}`}>
                  backtest {launchResult.backtestId}
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={() => setLaunchResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

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

      <Stack component="form" spacing={3} onSubmit={handleSubmit}>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Metadata</Typography>
            <TextField
              label="Name (optional)"
              value={backtestName}
              onChange={(event) => setBacktestName(event.target.value)}
              helperText="Helps you find this backtest later."
              slotProps={{ htmlInput: { maxLength: 256 } }}
              fullWidth
            />
          </Stack>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Launch mode</Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={launchMode === 'dataset'}
                  onChange={(_event, checked) => setLaunchMode(checked ? 'dataset' : 'legacy')}
                />
              }
              label={launchMode === 'dataset' ? 'Use existing dataset' : 'Use legacy selection'}
            />
            <Typography variant="body2" color="text.secondary">
              Dataset mode launches from a completed dataset manifest. Legacy mode uses manual symbols and date range widgets.
            </Typography>
          </Stack>
        </Paper>

        {launchMode === 'dataset' ? (
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">Dataset</Typography>
              <Autocomplete
                options={availableDatasets}
                getOptionLabel={(option) =>
                  `${option.id} — ${option.name ?? option.symbol} (${option.start_date} → ${option.end_date})`
                }
                value={selectedDataset}
                isOptionEqualToValue={(option, value) => option.id === value.id}
                onChange={(_event, value) => setSelectedDatasetId(value?.id ?? null)}
                loading={loadingDatasets}
                noOptionsText={
                  loadingDatasets
                    ? 'Loading datasets…'
                    : 'No completed datasets are available yet.'
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Existing dataset"
                    placeholder="Select a completed dataset"
                    helperText="Completed datasets appear here. If cached artifact paths are missing, launch will resolve them from storage before submitting."
                  />
                )}
              />
              {selectedDataset && (
                <Alert severity="info">
                  Dataset {selectedDataset.id} covers {selectedDataset.start_date} to {selectedDataset.end_date}.
                  {(!selectedDataset.dataset_parquet_path || !selectedDataset.manifest_path) && (
                    <>
                      {' '}
                      Artifact paths are not cached on this record yet, so launch will resolve them from the
                      dataset storage directory before submitting.
                    </>
                  )}
                </Alert>
              )}
              {showCommissionDragWarning && (
                <Alert severity="warning">
                  Intraday backtests with stake of 1 share and commission of 0.1% per side often
                  produce net losses even on small gross winners (~0.2% round-trip cost). Use stake
                  of at least 10 or lower commission for more meaningful intraday results.
                </Alert>
              )}
            </Stack>
          </Paper>
        ) : (
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">Legacy selection</Typography>
              <Stack spacing={1.5}>
                <Autocomplete
                  options={availableUniverses}
                  getOptionLabel={(option) => `${option.name} (${option.key})`}
                  value={selectedUniverse}
                  isOptionEqualToValue={(option, value) => option.key === value.key}
                  onChange={(_event, value) => setSelectedUniverseKey(value?.key ?? null)}
                  loading={loadingUniverses}
                  noOptionsText={
                    loadingUniverses
                      ? 'Loading universes…'
                      : 'No universes are available yet.'
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Universe"
                      placeholder="Choose a universe"
                      helperText="Select a registry or user universe, then sample from its constituents."
                    />
                  )}
                />
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ flex: 1 }}>
                      Sample size
                    </Typography>
                    <TextField
                      size="small"
                      type="number"
                      value={sampleSize}
                      onChange={(event) => {
                        const next = Number.parseInt(event.target.value, 10)
                        setSampleSize(Number.isFinite(next) && next > 0 ? next : 1)
                      }}
                      slotProps={{ htmlInput: { min: 1, max: 100, step: 1 } }}
                      sx={{ width: 140 }}
                    />
                  </Stack>
                  <Slider
                    value={sampleSize}
                    onChange={(_event, nextValue) => {
                      setSampleSize(Array.isArray(nextValue) ? nextValue[0] : nextValue)
                    }}
                    min={1}
                    max={100}
                    step={1}
                    valueLabelDisplay="auto"
                  />
                  <Typography variant="caption" color="text.secondary">
                    How many symbols to pull from the selected universe.
                  </Typography>
                </Stack>
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
                onChange={(_event, value) => {
                  setSymbols(normalizeSymbols(value))
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
              {showCommissionDragWarning && (
                <Alert severity="warning">
                  Intraday backtests with stake of 1 share and commission of 0.1% per side often
                  produce net losses even on small gross winners (~0.2% round-trip cost). Use stake
                  of at least 10 or lower commission for more meaningful intraday results.
                </Alert>
              )}
            </Stack>
          </Paper>
        )}

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <TuneIcon color="primary" />
              <Typography variant="h6">Triggers and optional overrides</Typography>
            </Stack>
            {loadingTriggers ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <CircularProgress size={20} />
                <Typography color="text.secondary">Loading triggers…</Typography>
              </Stack>
            ) : (
              <>
                <Autocomplete
                  multiple
                  options={triggers}
                  getOptionLabel={(option) => option.name}
                  value={selectedTriggers}
                  onChange={(_event, value) => handleTriggerSelectionChange(value)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Triggers"
                      helperText="Choose one or more triggers to expand against the symbol list."
                    />
                  )}
                />

                {selectedTriggers.map((strategy) => {
                  const params =
                    triggerOverrides[strategy.name] ?? buildStrategyParams(strategy, resolution)
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
                            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                              <Typography variant="subtitle1">{strategy.name}</Typography>
                              <Tooltip title="Open strategy documentation">
                                <span>
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<InfoOutlinedIcon fontSize="small" />}
                                    aria-label={`Open documentation for ${strategy.name}`}
                                    onClick={() => setDocumentationStrategy(strategy)}
                                    sx={{ textTransform: 'none' }}
                                  >
                                    Strategy docs
                                  </Button>
                                </span>
                              </Tooltip>
                            </Stack>
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
                              onChange={(value) => handleTriggerParamChange(strategy.name, name, value)}
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

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Model policy</Typography>
            <BacktestModelPolicyForm
              disabled={submitting}
              initialValue={prefillModelPolicy}
              onChange={setModelPolicy}
            />
          </Stack>
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <TuneIcon color="primary" />
              <Typography variant="h6">Exit rules</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Exit rules are evaluated in order while a position is open. The first rule that signals a close wins.
            </Typography>
            {loadingExitRules ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <CircularProgress size={20} />
                <Typography color="text.secondary">Loading exit rules…</Typography>
              </Stack>
            ) : (
              <>
                <Autocomplete
                  options={availableExitRulesToAdd}
                  getOptionLabel={(option) => option.name}
                  value={pendingExitRuleToAdd}
                  onChange={(_event, value) => addExitRule(value)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Add exit rule"
                      helperText="Pick one or more exit rules to apply to every trigger/symbol run."
                    />
                  )}
                />

                {selectedExitRules.length === 0 ? (
                  <Alert severity="warning">Choose at least one exit rule to launch a backtest.</Alert>
                ) : (
                  selectedExitRules.map((rule, index) => {
                    const params = exitRuleOverrides[rule.name] ?? buildStrategyParams(rule, resolution)
                    const overrideCount = Object.keys(buildOverrideParams(rule, params)).length
                    return (
                      <Paper key={rule.name} variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
                        <Stack spacing={2}>
                        <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <Box sx={{ pr: 1 }}>
                              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                                <Typography variant="subtitle1">
                                  {index + 1}. {rule.name}
                                </Typography>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  startIcon={<InfoOutlinedIcon fontSize="small" />}
                                  aria-label={`Open documentation for ${rule.name}`}
                                  onClick={() => setDocumentationStrategy(rule)}
                                  sx={{ textTransform: 'none' }}
                                >
                                  Rule docs
                                </Button>
                              </Stack>
                              <Typography variant="body2" color="text.secondary">
                                {rule.description}
                              </Typography>
                            </Box>
                            <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                              <Typography variant="caption" color="text.secondary" sx={{ pr: 1 }}>
                                {overrideCount} override{overrideCount === 1 ? '' : 's'}
                              </Typography>
                              <Button
                                size="small"
                                variant="text"
                                onClick={() => moveExitRule(rule.name, -1)}
                                disabled={submitting || index === 0}
                                startIcon={<ArrowUpwardIcon fontSize="small" />}
                              >
                                Up
                              </Button>
                              <Button
                                size="small"
                                variant="text"
                                onClick={() => moveExitRule(rule.name, 1)}
                                disabled={submitting || index === selectedExitRules.length - 1}
                                startIcon={<ArrowDownwardIcon fontSize="small" />}
                              >
                                Down
                              </Button>
                              <Button
                                size="small"
                                color="inherit"
                                variant="text"
                                onClick={() => removeExitRule(rule.name)}
                                disabled={submitting}
                                startIcon={<DeleteOutlineIcon fontSize="small" />}
                              >
                                Remove
                              </Button>
                            </Stack>
                          </Stack>
                          <Box
                            sx={{
                              display: 'grid',
                              gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                              gap: 2,
                            }}
                          >
                            {Object.entries(rule.parameters).map(([name, meta]) => (
                              <ParameterField
                                key={`${rule.name}-${name}`}
                                name={name}
                                meta={meta}
                                value={params[name]}
                                disabled={submitting}
                                onChange={(value) => handleExitRuleParamChange(rule.name, name, value)}
                              />
                            ))}
                          </Box>
                        </Stack>
                      </Paper>
                    )
                  })
                )}
              </>
            )}
          </Stack>
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Output and logging</Typography>
            <Typography variant="body2" color="text.secondary">
              Control what is persisted in each backtest run. Platform defaults can be reset from
              settings.
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ flexWrap: 'wrap' }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={submitAnalyzers.include_equity_curve}
                    onChange={(_event, checked) =>
                      setSubmitAnalyzers((current) => ({
                        ...current,
                        include_equity_curve: checked,
                      }))
                    }
                  />
                }
                label="Include equity curve"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={submitAnalyzers.include_trade_log}
                    onChange={(_event, checked) =>
                      setSubmitAnalyzers((current) => ({
                        ...current,
                        include_trade_log: checked,
                      }))
                    }
                  />
                }
                label="Include trade log"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={submitAnalyzers.include_order_log}
                    onChange={(_event, checked) =>
                      setSubmitAnalyzers((current) => ({
                        ...current,
                        include_order_log: checked,
                      }))
                    }
                  />
                }
                label="Include order log"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={submitAnalyzers.include_candidate_log}
                    onChange={(_event, checked) =>
                      setSubmitAnalyzers((current) => ({
                        ...current,
                        include_candidate_log: checked,
                        include_risk_auxiliary: checked ? current.include_risk_auxiliary : false,
                      }))
                    }
                  />
                }
                label="Include candidate log"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={submitAnalyzers.include_risk_auxiliary}
                    disabled={!submitAnalyzers.include_candidate_log}
                    onChange={(_event, checked) =>
                      setSubmitAnalyzers((current) => ({
                        ...current,
                        include_candidate_log: checked ? true : current.include_candidate_log,
                        include_risk_auxiliary: checked,
                      }))
                    }
                  />
                }
                label="Build risk labels and features"
              />
            </Stack>
            {submitAnalyzers.include_candidate_log && (
              <Alert severity="info">
                Candidate logging records every entry signal (traded and rejected) and increases
                backtest output size.
                {submitAnalyzers.include_risk_auxiliary
                  ? ' Risk auxiliary adds outcome-label and feature-snapshot parquet sidecars.'
                  : ''}
              </Alert>
            )}
            <Link
              component="button"
              type="button"
              variant="body2"
              onClick={() => setSubmitAnalyzers(platformSettings.backtest_defaults.analyzers)}
              sx={{ alignSelf: 'flex-start' }}
            >
              Reset to platform defaults
            </Link>
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
            <Typography color="text.secondary">
              {launchMode === 'dataset'
                ? selectedDataset
                  ? `${selectedDataset.name ?? selectedDataset.id} · ${selectedDataset.start_date} → ${selectedDataset.end_date}`
                  : 'Choose a dataset to review its date range.'
                : formatReviewDateRange(startDate, endDate)}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
              <Box>
                <Typography variant="overline">Mode</Typography>
                <Typography variant="h5">{launchMode === 'dataset' ? 'Dataset' : 'Legacy'}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Triggers</Typography>
                <Typography variant="h5">{selectedTriggers.length}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Exit rules</Typography>
                <Typography variant="h5">{selectedExitRuleNames.length}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Model policy</Typography>
                <Chip
                  size="small"
                  label={
                    modelPolicy
                      ? `${modelPolicy.forecast_model ? 'forecast' : ''}${modelPolicy.forecast_model && modelPolicy.risk_model ? ' + ' : ''}${modelPolicy.risk_model ? 'risk' : ''}`
                      : 'trigger-only'
                  }
                  color={modelPolicy ? 'primary' : 'default'}
                />
              </Box>
              <Box>
                <Typography variant="overline">Expanded runs</Typography>
                <Typography variant="h5">{totalRuns}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Candidate log</Typography>
                <Chip
                  size="small"
                  label={submitAnalyzers.include_candidate_log ? 'on' : 'off'}
                  color={submitAnalyzers.include_candidate_log ? 'primary' : 'default'}
                />
              </Box>
            </Stack>
            {launchMode === 'dataset'
              ? !selectedDataset && <Alert severity="warning">Choose a completed dataset before launching.</Alert>
              : !hasValidDateRange && <Alert severity="warning">End date must be on or after start date.</Alert>}
            <Box>
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={
                  submitting ||
                  loadingTriggers ||
                  loadingExitRules ||
                  loadingPrefill ||
                  (launchMode === 'dataset' ? !selectedDataset : !hasValidDateRange || symbols.length === 0) ||
                  selectedTriggers.length === 0 ||
                  selectedExitRuleNames.length === 0
                }
              >
                {submitting ? 'Submitting…' : 'Launch backtest'}
              </Button>
            </Box>
          </Stack>
        </Paper>

        <Dialog
          open={documentationStrategy !== null}
          onClose={() => setDocumentationStrategy(null)}
          fullWidth
          maxWidth="md"
        >
          <DialogTitle sx={{ pb: 1 }}>
            {documentationStrategy?.name} documentation
          </DialogTitle>
          <DialogContent dividers>
            {documentationStrategy && (
              <Stack spacing={3}>
                <Box>
                  <Typography variant="overline" color="text.secondary">
                    Overview
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    {documentationStrategy.description}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="overline" color="text.secondary">
                    How it works
                  </Typography>
                  <Stack spacing={1.5} sx={{ mt: 0.75 }}>
                    {documentationStrategy.documentation.split('\n\n').map((paragraph) => (
                      <Typography key={paragraph} variant="body2" sx={{ whiteSpace: 'pre-line' }}>
                        {paragraph}
                      </Typography>
                    ))}
                  </Stack>
                </Box>
                {Object.keys(documentationStrategy.parameters).length > 0 && (
                  <Box>
                    <Typography variant="overline" color="text.secondary">
                      Parameters
                    </Typography>
                    <Box
                      sx={{
                        mt: 1,
                        border: 1,
                        borderColor: 'divider',
                        borderRadius: 1,
                        overflow: 'hidden',
                      }}
                    >
                      <Box
                        sx={{
                          display: 'grid',
                          gridTemplateColumns: { xs: '1fr', md: '180px 1fr 120px 110px' },
                          bgcolor: 'background.default',
                          borderBottom: 1,
                          borderColor: 'divider',
                          px: 2,
                          py: 1,
                          gap: 1,
                        }}
                      >
                        <Typography variant="caption" color="text.secondary">
                          Parameter
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Details
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ textAlign: { xs: 'left', md: 'right' } }}
                        >
                          Default
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ textAlign: { xs: 'left', md: 'center' } }}
                        >
                          Required
                        </Typography>
                      </Box>
                      {Object.entries(documentationStrategy.parameters).map(([name, meta]) => (
                        <Box
                          key={name}
                          sx={{
                            display: 'grid',
                            gridTemplateColumns: { xs: '1fr', md: '180px 1fr 120px 110px' },
                            px: 2,
                            py: 1.25,
                            gap: 1,
                            borderBottom: 1,
                            borderColor: 'divider',
                            '&:last-of-type': { borderBottom: 0 },
                          }}
                        >
                          <Box>
                            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                              {name}
                            </Typography>
                            {meta.title && (
                              <Typography variant="caption" color="text.secondary">
                                {meta.title}
                              </Typography>
                            )}
                          </Box>
                          <Typography variant="body2" color="text.secondary">
                            {meta.description ?? 'No additional description provided.'}
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{ textAlign: { xs: 'left', md: 'right' } }}
                          >
                            {formatDefaultValue(meta.default)}
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{ textAlign: { xs: 'left', md: 'center' } }}
                          >
                            {meta.required ? 'Yes' : 'No'}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </Box>
                )}
              </Stack>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDocumentationStrategy(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Stack>
    </Stack>
  )
}
