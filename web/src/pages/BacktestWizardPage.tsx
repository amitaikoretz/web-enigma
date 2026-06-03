import AddIcon from '@mui/icons-material/Add'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
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
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { createBacktest, fetchBacktestInputConfig } from '../api/backtests'
import { fetchExitRules, fetchStrategies } from '../api/strategies'
import { createUserUniverse, fetchUniverseConstituents, fetchUniverses } from '../api/universes'
import { useSettings } from '../settings/useSettings'
import type { BacktestFeed } from '../types/backtests'
import type { Resolution } from '../types/marketData'
import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'
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

interface LaunchResultState {
  status: 'success' | 'failed'
  message: string
  backtestId?: string
}

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
  const [symbols, setSymbols] = useState<string[]>(platformSettings.backtest_defaults.symbols_seed_list)
  const [availableUniverses, setAvailableUniverses] = useState<SymbolUniverse[]>([])
  const [loadingUniverses, setLoadingUniverses] = useState(false)
  const [selectedUniverseKeys, setSelectedUniverseKeys] = useState<string[]>([])
  const [expandingUniverses, setExpandingUniverses] = useState(false)
  const [createUniverseDialogOpen, setCreateUniverseDialogOpen] = useState(false)
  const [createUniverseDraft, setCreateUniverseDraft] = useState({
    name: '',
    description: '',
    isActive: true,
  })
  const [creatingUniverse, setCreatingUniverse] = useState(false)
  const [addConstituentsDialogOpen, setAddConstituentsDialogOpen] = useState(false)
  const [expandedUniverseSymbols, setExpandedUniverseSymbols] = useState<string[]>([])
  const [addConstituentsDraft, setAddConstituentsDraft] = useState({
    subsamplePct: 100,
    shuffle: true,
    seed: '',
    includeText: '',
    excludeText: '',
  })
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
  const [pendingExitRuleToAdd, setPendingExitRuleToAdd] = useState<StrategyMetadata | null>(null)
  const [submitBroker, setSubmitBroker] = useState(platformSettings.backtest_defaults.broker)
  const [submitAnalyzers, setSubmitAnalyzers] = useState(platformSettings.backtest_defaults.analyzers)
  const [submitExecution, setSubmitExecution] = useState(platformSettings.backtest_defaults.execution)

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

    const nextStartDate = searchParams.get('start_date')
    const nextEndDate = searchParams.get('end_date')
    const nextResolution = searchParams.get('resolution')
    const nextFeed = searchParams.get('feed')

    setSymbols(parsedSymbols)
    if (nextStartDate) {
      setStartDate(dayjs(nextStartDate))
    }
    if (nextEndDate) {
      setEndDate(dayjs(nextEndDate))
    }
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

  const reloadUniverses = async () => {
    setLoadingUniverses(true)
    try {
      const items = await fetchUniverses(true)
      setAvailableUniverses(items)
    } catch {
      setAvailableUniverses([])
    } finally {
      setLoadingUniverses(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoadingUniverses(true)
    void fetchUniverses(true)
      .then((items) => {
        if (cancelled) {
          return
        }
        setAvailableUniverses(items)
      })
      .catch(() => {
        if (!cancelled) {
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

  const asOfDateForUniverses = useMemo(() => {
    const resolved = startDate ?? dayjs()
    return resolved.format('YYYY-MM-DD')
  }, [startDate])

  const parseSymbolFilterText = (value: string) =>
    value
      .split(/[\n,]+/g)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean)

  const shuffleWithSeed = (items: string[], seedText: string) => {
    const seedBase = seedText.trim() || 'seed'
    const mix = (input: string) => {
      let h = 2166136261
      for (let i = 0; i < input.length; i += 1) {
        h ^= input.charCodeAt(i)
        h = Math.imul(h, 16777619)
      }
      return h >>> 0
    }
    let state = mix(seedBase)
    const next = () => {
      state = (Math.imul(1664525, state) + 1013904223) >>> 0
      return state / 2 ** 32
    }
    const copy = [...items]
    for (let i = copy.length - 1; i > 0; i -= 1) {
      const j = Math.floor(next() * (i + 1))
      ;[copy[i], copy[j]] = [copy[j], copy[i]]
    }
    return copy
  }

  const subsampleCount = (count: number, pct: number) => {
    const normalizedPct = Math.max(1, Math.min(100, Math.round(pct)))
    if (count <= 0) {
      return 0
    }
    if (normalizedPct === 100) {
      return count
    }
    return Math.max(1, Math.floor((count * normalizedPct) / 100))
  }

  const filteredExpandedSymbolsBeforeSampling = useMemo(() => {
    const include = parseSymbolFilterText(addConstituentsDraft.includeText)
    const exclude = new Set(parseSymbolFilterText(addConstituentsDraft.excludeText))
    const includeSet = include.length > 0 ? new Set(include) : null
    const base = expandedUniverseSymbols.filter((item) => (includeSet ? includeSet.has(item) : true))
    const filtered = base.filter((item) => !exclude.has(item))
    return addConstituentsDraft.shuffle ? shuffleWithSeed(filtered, addConstituentsDraft.seed) : filtered
  }, [addConstituentsDraft.excludeText, addConstituentsDraft.includeText, addConstituentsDraft.seed, addConstituentsDraft.shuffle, expandedUniverseSymbols])

  const filteredExpandedSymbols = useMemo(() => {
    const pct = Math.max(1, Math.min(100, Math.round(addConstituentsDraft.subsamplePct)))
    const target = subsampleCount(filteredExpandedSymbolsBeforeSampling.length, pct)
    return filteredExpandedSymbolsBeforeSampling.slice(0, target)
  }, [addConstituentsDraft.subsamplePct, filteredExpandedSymbolsBeforeSampling])

  const applyUniverseSelection = async (mode: 'add' | 'replace') => {
    if (selectedUniverseKeys.length === 0) {
      return
    }
    setError(null)
    setExpandingUniverses(true)
    try {
      const selectedUniverses = selectedUniverseKeys
        .map((key) => availableUniverses.find((item) => item.key === key))
        .filter((item): item is NonNullable<typeof item> => Boolean(item))

      const expansions = await Promise.all(
        selectedUniverses.map((universe) => {
          const asOf = universe.kind === 'user' ? dayjs().format('YYYY-MM-DD') : asOfDateForUniverses
          return fetchUniverseConstituents(universe.key, asOf)
        }),
      )
      const expanded = expansions.flatMap((item) => item.symbols)
      if (expanded.length === 0) {
        const keys = selectedUniverseKeys.join(', ')
        setError(
          `No constituents found for ${keys}. ` +
            'Sync the universe registry and run a universe refresh first (user universes use today, others use the start date).',
        )
        return
      }
      const normalized = expanded
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean)
      const dedupedExpanded = normalized.filter((item, idx, arr) => arr.indexOf(item) === idx)
      if (mode === 'add') {
        setExpandedUniverseSymbols(dedupedExpanded)
        setAddConstituentsDraft({
          subsamplePct: 100,
          shuffle: true,
          seed: '',
          includeText: '',
          excludeText: '',
        })
        setAddConstituentsDialogOpen(true)
        return
      }
      const merged = [...dedupedExpanded]
      setSymbols(merged)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to expand universe')
    } finally {
      setExpandingUniverses(false)
    }
  }

  const handleConfirmAddConstituents = () => {
    if (filteredExpandedSymbols.length === 0) {
      setError('No symbols matched the filters.')
      return
    }
    const merged = [...symbols, ...filteredExpandedSymbols]
    const deduped = merged.filter((item, idx, arr) => arr.indexOf(item) === idx)
    setSymbols(deduped)
    setAddConstituentsDialogOpen(false)
  }

  const openCreateUniverseDialog = () => {
    if (symbols.length === 0) {
      setError('Add at least one symbol before creating a universe.')
      return
    }
    setError(null)
    setCreateUniverseDraft({ name: '', description: '', isActive: true })
    setCreateUniverseDialogOpen(true)
  }

  const handleCreateUniverse = async () => {
    const name = createUniverseDraft.name.trim()
    if (!name) {
      setError('Universe name is required.')
      return
    }
    if (symbols.length === 0) {
      setError('No symbols selected.')
      return
    }

    setCreatingUniverse(true)
    setError(null)
    try {
      const created = await createUserUniverse({
        name,
        description: createUniverseDraft.description.trim() || null,
        symbols,
        is_active: createUniverseDraft.isActive,
      })
      setCreateUniverseDialogOpen(false)
      await reloadUniverses()
      setSelectedUniverseKeys((prev) =>
        prev.includes(created.key) ? prev : [...prev, created.key],
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create universe')
    } finally {
      setCreatingUniverse(false)
    }
  }

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

        setSymbols(prefill.symbols)
        setStartDate(dayjs(prefill.startDate))
        setEndDate(dayjs(prefill.endDate))
        setResolution(prefill.resolution)
        setFeed(prefill.feed)
        setSelectedTriggerNames(nextTriggerNames)
        setTriggerOverrides(nextTriggerOverrides)
        setSelectedExitRuleNames(nextExitRuleNames)
        setExitRuleOverrides(nextExitRuleOverrides)
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

  const selectedExitRules = useMemo(
    () =>
      selectedExitRuleNames
        .map((name) => exitRules.find((rule) => rule.name === name) ?? null)
        .filter((rule): rule is StrategyMetadata => rule !== null),
    [selectedExitRuleNames, exitRules],
  )

  const totalRuns = symbols.length * selectedTriggers.length
  const hasValidDateRange =
    startDate !== null && endDate !== null && !endDate.isBefore(startDate, 'day')

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
    if (!startDate || !endDate || !hasValidDateRange) {
      setError('Choose a valid date range before submitting.')
      return
    }
    if (symbols.length === 0 || selectedTriggers.length === 0 || selectedExitRuleNames.length === 0) {
      setError('Add at least one symbol, trigger, and exit rule before submitting.')
      return
    }

    if (platformSettings.platform_behavior.confirm_before_launch) {
      const confirmed = window.confirm(
        `Launch ${totalRuns} backtest run${totalRuns === 1 ? '' : 's'} using ${symbols.length} symbol${symbols.length === 1 ? '' : 's'} and ${selectedTriggers.length} trigger${selectedTriggers.length === 1 ? '' : 's'}?`,
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
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        resolution,
        feed,
        symbols,
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
      <Stack spacing={0.5}>
        <Typography variant="h4">Backtest Wizard</Typography>
        <Typography color="text.secondary">
          Build a matrix of symbols and triggers, then let the API run it in the background.
        </Typography>
      </Stack>

      {prefillSourceId && (
        <Alert severity="info">
          Prefilled from backtest `{prefillSourceId}`. Edit any settings below before launching.
        </Alert>
      )}

      {!prefillSourceId && downloadPrefillSymbols && (
        <Alert severity="info">
          Prefilled from a market data download job. Choose triggers and exit rules below before launching.
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
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1 }}>
          <Button onClick={() => setLaunchResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {error && <Alert severity="error">{error}</Alert>}

      <Dialog
        open={addConstituentsDialogOpen}
        onClose={expandingUniverses ? undefined : () => setAddConstituentsDialogOpen(false)}
        aria-labelledby="add-constituents-title"
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
              maxWidth: 680,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="add-constituents-title" sx={{ pb: 1 }}>
          Add constituents ({filteredExpandedSymbols.length} of {expandedUniverseSymbols.length})
        </DialogTitle>
        <DialogContent sx={{ pt: 0 }}>
          <Stack spacing={2}>
            <Box>
              <Typography variant="subtitle2">Subsample</Typography>
              <Slider
                value={addConstituentsDraft.subsamplePct}
                onChange={(_e, value) =>
                  setAddConstituentsDraft((prev) => ({ ...prev, subsamplePct: value as number }))
                }
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => {
                  const baseCount = filteredExpandedSymbolsBeforeSampling.length
                  const keep = subsampleCount(baseCount, Number(value))
                  return `${keep} / ${baseCount}`
                }}
                min={1}
                max={100}
                disabled={expandingUniverses}
                sx={{ mt: 1.5, mb: 0.5 }}
              />
              <Typography variant="caption" color="text.secondary">
                Keep {filteredExpandedSymbols.length} of {filteredExpandedSymbolsBeforeSampling.length} matched symbols.
              </Typography>
            </Box>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Include (optional)"
                value={addConstituentsDraft.includeText}
                onChange={(e) => setAddConstituentsDraft((prev) => ({ ...prev, includeText: e.target.value }))}
                helperText="Comma/newline separated symbols. Leave empty to include all."
                disabled={expandingUniverses}
                fullWidth
              />
              <TextField
                label="Exclude (optional)"
                value={addConstituentsDraft.excludeText}
                onChange={(e) => setAddConstituentsDraft((prev) => ({ ...prev, excludeText: e.target.value }))}
                helperText="Comma/newline separated symbols to remove."
                disabled={expandingUniverses}
                fullWidth
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={addConstituentsDraft.shuffle}
                    onChange={(_e, checked) => setAddConstituentsDraft((prev) => ({ ...prev, shuffle: checked }))}
                    disabled={expandingUniverses}
                  />
                }
                label="Shuffle before sampling"
              />
              <TextField
                label="Seed (optional)"
                value={addConstituentsDraft.seed}
                onChange={(e) => setAddConstituentsDraft((prev) => ({ ...prev, seed: e.target.value }))}
                disabled={expandingUniverses || !addConstituentsDraft.shuffle}
                placeholder="42"
                sx={{ flex: 1 }}
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, gap: 1 }}>
          <Button
            onClick={() => setAddConstituentsDialogOpen(false)}
            disabled={expandingUniverses}
            variant="outlined"
            color="inherit"
          >
            Cancel
          </Button>
          <Button
            onClick={handleConfirmAddConstituents}
            disabled={expandingUniverses || filteredExpandedSymbols.length === 0}
            variant="contained"
          >
            Add {filteredExpandedSymbols.length}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={createUniverseDialogOpen}
        onClose={creatingUniverse ? undefined : () => setCreateUniverseDialogOpen(false)}
        aria-labelledby="create-universe-title"
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
              maxWidth: 620,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="create-universe-title" sx={{ pb: 1 }}>
          Create universe from symbols ({symbols.length})
        </DialogTitle>
        <DialogContent sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <TextField
              label="Name"
              value={createUniverseDraft.name}
              onChange={(e) => setCreateUniverseDraft((prev) => ({ ...prev, name: e.target.value }))}
              disabled={creatingUniverse}
              autoFocus
              placeholder="My Basket"
            />
            <TextField
              label="Description"
              value={createUniverseDraft.description}
              onChange={(e) => setCreateUniverseDraft((prev) => ({ ...prev, description: e.target.value }))}
              disabled={creatingUniverse}
            />
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Switch
                checked={createUniverseDraft.isActive}
                onChange={(_e, checked) => setCreateUniverseDraft((prev) => ({ ...prev, isActive: checked }))}
                disabled={creatingUniverse}
              />
              <Typography>Active</Typography>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, gap: 1 }}>
          <Button
            onClick={() => setCreateUniverseDialogOpen(false)}
            disabled={creatingUniverse}
            variant="outlined"
            color="inherit"
          >
            Cancel
          </Button>
          <Button
            onClick={() => void handleCreateUniverse()}
            disabled={creatingUniverse || symbols.length === 0 || !createUniverseDraft.name.trim()}
            variant="contained"
            startIcon={creatingUniverse ? <CircularProgress size={16} color="inherit" /> : <AddIcon />}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

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
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="h6">Universe</Typography>
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'flex-start' } }}>
              <Autocomplete
                multiple
                options={availableUniverses}
                getOptionLabel={(option) => {
                  const refresh = option.latest_refresh_as_of
                    ? ` (refreshed ${option.latest_refresh_as_of})`
                    : ''
                  return `${option.key} — ${option.name}${refresh}`
                }}
                value={availableUniverses.filter((u) => selectedUniverseKeys.includes(u.key))}
                onChange={(_event, value) => setSelectedUniverseKeys(value.map((item) => item.key))}
                loading={loadingUniverses}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Universes"
                    placeholder="Select one or more universes"
                    helperText={`Expanded as-of ${asOfDateForUniverses} (user universes expand using today).`}
                  />
                )}
                sx={{ flex: 1 }}
              />
              <Stack direction="row" spacing={1} sx={{ pt: { md: 0.5 } }}>
                <Button
                  variant="outlined"
                  onClick={() => void applyUniverseSelection('add')}
                  disabled={selectedUniverseKeys.length === 0 || expandingUniverses}
                >
                  Add constituents
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => void applyUniverseSelection('replace')}
                  disabled={selectedUniverseKeys.length === 0 || expandingUniverses}
                >
                  Replace symbols
                </Button>
                <Button variant="contained" onClick={openCreateUniverseDialog} disabled={symbols.length === 0}>
                  Create Universe
                </Button>
              </Stack>
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
                              <Typography variant="subtitle1">
                                {index + 1}. {rule.name}
                              </Typography>
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
            <Typography color="text.secondary">{formatDateRange(startDate, endDate)}</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
              <Box>
                <Typography variant="overline">Symbols</Typography>
                <Typography variant="h5">{symbols.length}</Typography>
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
                  loadingTriggers ||
                  loadingExitRules ||
                  loadingPrefill ||
                  !hasValidDateRange ||
                  symbols.length === 0 ||
                  selectedTriggers.length === 0 ||
                  selectedExitRuleNames.length === 0
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
