import AddIcon from '@mui/icons-material/Add'
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
import { useNavigate, useSearchParams } from 'react-router-dom'

import { createBacktest, fetchBacktestInputConfig } from '../api/backtests'
import { fetchStrategies } from '../api/strategies'
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
  const [searchParams] = useSearchParams()
  const prefillFromId = searchParams.get('from')
  const downloadPrefillSymbols = searchParams.get('symbols')
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([])
  const [loadingStrategies, setLoadingStrategies] = useState(true)
  const [loadingPrefill, setLoadingPrefill] = useState(Boolean(prefillFromId))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
  const [selectedStrategyNames, setSelectedStrategyNames] = useState<string[]>([])
  const [strategyOverrides, setStrategyOverrides] = useState<Record<string, Record<string, unknown>>>({})
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
        setStrategies(items)
        if (!prefillFromId && items[0]) {
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
    if (!prefillFromId || loadingStrategies || strategies.length === 0) {
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

        const nextOverrides: Record<string, Record<string, unknown>> = {}
        const nextStrategyNames: string[] = []
        for (const selection of prefill.strategies) {
          const strategy = strategies.find((item) => item.name === selection.name)
          if (!strategy) {
            continue
          }
          nextStrategyNames.push(strategy.name)
          nextOverrides[strategy.name] = {
            ...buildStrategyParams(strategy, prefill.resolution),
            ...selection.params,
          }
        }

        if (nextStrategyNames.length === 0) {
          throw new Error('None of the original strategies are available on this server.')
        }

        setSymbols(prefill.symbols)
        setStartDate(dayjs(prefill.startDate))
        setEndDate(dayjs(prefill.endDate))
        setResolution(prefill.resolution)
        setFeed(prefill.feed)
        setSelectedStrategyNames(nextStrategyNames)
        setStrategyOverrides(nextOverrides)
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
  }, [prefillFromId, loadingStrategies, strategies, platformSettings.backtest_defaults])

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
    setStrategyOverrides(() => {
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
        submitBroker.commission,
        selectedStrategies,
        strategyOverrides,
      ),
    [resolution, submitBroker.commission, selectedStrategies, strategyOverrides],
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
        name: backtestName.trim() ? backtestName.trim() : null,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        resolution,
        feed,
        symbols,
        strategies: selectedStrategies.map((strategy) => ({
          name: strategy.name,
          params: buildOverrideParams(strategy, strategyOverrides[strategy.name] ?? {}),
        })),
        broker: submitBroker,
        analyzers: submitAnalyzers,
        execution: submitExecution,
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

      {prefillSourceId && (
        <Alert severity="info">
          Prefilled from backtest `{prefillSourceId}`. Edit any settings below before launching.
        </Alert>
      )}

      {!prefillSourceId && downloadPrefillSymbols && (
        <Alert severity="info">
          Prefilled from a market data download job. Choose strategies below before launching.
        </Alert>
      )}

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
                <Typography variant="overline">Strategies</Typography>
                <Typography variant="h5">{selectedStrategies.length}</Typography>
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
                  loadingStrategies ||
                  loadingPrefill ||
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
