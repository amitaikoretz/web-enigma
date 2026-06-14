import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import {
  Alert,
  Box,
  Button,
  Autocomplete,
  Chip,
  FormControlLabel,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Slider,
  Switch,
  Stack,
  TextField,
  Typography,
  Link,
} from '@mui/material'
import type { SxProps, Theme } from '@mui/material/styles'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

import { createDataset, fetchDatasetDetail } from '../api/datasets'
import { fetchUniverses, fetchUniverseConstituents } from '../api/universes'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useSettings } from '../settings/useSettings'
import type { DatasetDetailResponse, DatasetOptionsFeed, DatasetProvider, DatasetResolution } from '../types/datasets'
import type { SymbolUniverse } from '../types/universes'

const RESOLUTIONS: DatasetResolution[] = ['1m', '5m', '15m', '1h', '1d']
const PROVIDERS: DatasetProvider[] = ['alpaca', 'yahoo']
const DEFAULT_MAX_SYMBOLS_PER_SHARD = 10

const fieldSx: SxProps<Theme> = { minWidth: 0 }

function normalizeSymbols(values: string[]): string[] {
  return values
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .filter((item, index, allValues) => allValues.indexOf(item) === index)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

export function DatasetWizardPage() {
  const location = useLocation()
  const { platformSettings } = useSettings()
  const [symbols, setSymbols] = useState<string[]>(
    normalizeSymbols(platformSettings.backtest_defaults.symbols_seed_list),
  )
  const [availableUniverses, setAvailableUniverses] = useState<SymbolUniverse[]>([])
  const [loadingUniverses, setLoadingUniverses] = useState(false)
  const [selectedUniverseKey, setSelectedUniverseKey] = useState<string | null>(null)
  const [sampleDialogOpen, setSampleDialogOpen] = useState(false)
  const [sampleSize, setSampleSize] = useState(1)
  const [samplingUniverse, setSamplingUniverse] = useState(false)
  const [loadingUniverseSymbols, setLoadingUniverseSymbols] = useState(false)
  const [universeSymbols, setUniverseSymbols] = useState<string[]>([])
  const [sampledSymbols, setSampledSymbols] = useState<string[]>([])
  const [chosenSampleSymbols, setChosenSampleSymbols] = useState<string[]>([])
  const [name, setName] = useState('')
  const [provider, setProvider] = useState<DatasetProvider>('alpaca')
  const [resolution, setResolution] = useState<DatasetResolution>(platformSettings.backtest_defaults.resolution)
  const [includeOptions, setIncludeOptions] = useState(false)
  const [optionsFeed, setOptionsFeed] = useState<DatasetOptionsFeed>('indicative')
  const [maxSymbolsPerShard, setMaxSymbolsPerShard] = useState<number>(DEFAULT_MAX_SYMBOLS_PER_SHARD)
  const [startDate, setStartDate] = useState<Dayjs | null>(dayjs().subtract(30, 'day'))
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [error, setError] = useState<string | null>(null)
  const [prefillSourceId, setPrefillSourceId] = useState<string | null>(null)
  const [prefillLoading, setPrefillLoading] = useState(false)
  const [prefillError, setPrefillError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [launchResult, setLaunchResult] = useState<
    | {
        status: 'success'
        message: string
        datasetId: string
      }
    | {
        status: 'failed'
        message: string
      }
    | null
  >(null)

  const selectedUniverse = useMemo(
    () => availableUniverses.find((item) => item.key === selectedUniverseKey) ?? null,
    [availableUniverses, selectedUniverseKey],
  )
  const defaultSymbols = useMemo(
    () => normalizeSymbols(platformSettings.backtest_defaults.symbols_seed_list),
    [platformSettings.backtest_defaults.symbols_seed_list.join('\u0000')],
  )
  const defaultResolution = platformSettings.backtest_defaults.resolution

  const primarySymbol = symbols[0] ?? platformSettings.backtest_defaults.symbols_seed_list[0] ?? 'AAPL'
  const prefillFromId = useMemo(() => new URLSearchParams(location.search).get('from'), [location.search])

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
        if (cancelled) {
          return
        }
        setAvailableUniverses([])
        setError(err instanceof Error ? err.message : 'Failed to load universes')
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
    if (selectedUniverseKey === null && availableUniverses.length === 1) {
      setSelectedUniverseKey(availableUniverses[0].key)
    }
  }, [availableUniverses, selectedUniverseKey])

  useEffect(() => {
    if (!prefillFromId) {
      setPrefillSourceId(null)
      setPrefillLoading(false)
      setPrefillError(null)
      return undefined
    }

    let cancelled = false
    setPrefillLoading(true)
    setPrefillError(null)

    void fetchDatasetDetail(prefillFromId)
      .then((response: DatasetDetailResponse) => {
        if (cancelled) {
          return
        }

        const metadata = response.metadata
        const params = isRecord(metadata.params_json) ? metadata.params_json : {}
        const parsedSymbols = Array.isArray(params.symbols)
          ? normalizeSymbols(params.symbols.filter((item): item is string => typeof item === 'string'))
          : []
        const fallbackSymbol =
          typeof params.symbol === 'string' && params.symbol.trim()
            ? params.symbol.trim().toUpperCase()
            : null
        const nextSymbols = parsedSymbols.length > 0 ? parsedSymbols : fallbackSymbol ? [fallbackSymbol] : defaultSymbols
        const nextProvider =
          typeof params.provider === 'string' && PROVIDERS.includes(params.provider as DatasetProvider)
            ? (params.provider as DatasetProvider)
            : 'alpaca'
        const nextResolution =
          typeof params.resolution === 'string' &&
          RESOLUTIONS.includes(params.resolution as DatasetResolution)
            ? (params.resolution as DatasetResolution)
            : defaultResolution
        const nextName = typeof params.name === 'string' ? params.name : ''
        const nextStartDate = typeof params.start_date === 'string' ? dayjs(params.start_date) : null
        const nextEndDate = typeof params.end_date === 'string' ? dayjs(params.end_date) : null
        const nextMaxSymbolsPerShard =
          typeof params.max_symbols_per_shard === 'number' && Number.isFinite(params.max_symbols_per_shard)
            ? Math.max(1, Math.floor(params.max_symbols_per_shard))
            : DEFAULT_MAX_SYMBOLS_PER_SHARD
        const nextOptions = isRecord(params.options) ? params.options : {}
        const nextIncludeOptions = Boolean(nextOptions.enabled)
        const nextOptionsFeed =
          typeof nextOptions.feed === 'string' && (nextOptions.feed === 'indicative' || nextOptions.feed === 'opra')
            ? (nextOptions.feed as DatasetOptionsFeed)
            : 'indicative'

        setSymbols(nextSymbols.length > 0 ? nextSymbols : defaultSymbols)
        setName(nextName)
        setProvider(nextProvider)
        setResolution(nextResolution)
        setIncludeOptions(nextIncludeOptions)
        setOptionsFeed(nextOptionsFeed)
        setMaxSymbolsPerShard(nextMaxSymbolsPerShard)
        setStartDate(nextStartDate?.isValid() ? nextStartDate : null)
        setEndDate(nextEndDate?.isValid() ? nextEndDate : null)
        setPrefillSourceId(metadata.id)
      })
      .catch((err) => {
        if (!cancelled) {
          setPrefillError(err instanceof Error ? err.message : 'Failed to load dataset prefill')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPrefillLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [defaultResolution, defaultSymbols, prefillFromId])

  useEffect(() => {
    let cancelled = false
    if (!sampleDialogOpen || !selectedUniverse) {
      setUniverseSymbols([])
      setSampledSymbols([])
      setChosenSampleSymbols([])
      return () => {
        cancelled = true
      }
    }

    setLoadingUniverseSymbols(true)
    const asOf = startDate?.format('YYYY-MM-DD') ?? dayjs().format('YYYY-MM-DD')
    void fetchUniverseConstituents(selectedUniverse.key, asOf)
      .then((constituents) => {
        if (cancelled) {
          return
        }
        const normalized = normalizeSymbols(constituents.symbols)
        setUniverseSymbols(normalized)
        setSampleSize((current) => Math.min(Math.max(current, 1), Math.max(normalized.length, 1)))
      })
      .catch((err) => {
        if (cancelled) {
          return
        }
        setUniverseSymbols([])
        setSampledSymbols([])
        setChosenSampleSymbols([])
        setError(err instanceof Error ? err.message : 'Failed to load universe symbols')
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingUniverseSymbols(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [sampleDialogOpen, selectedUniverse, startDate])

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!startDate || !endDate || endDate.isBefore(startDate, 'day')) {
      setError('Choose a valid date range.')
      return
    }
    setError(null)
    setConfirmOpen(true)
  }

  async function confirmSubmit() {
    if (!startDate || !endDate) {
      setError('Choose a valid date range.')
      setConfirmOpen(false)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const response = await createDataset({
        symbol: primarySymbol,
        symbols,
        max_symbols_per_shard: maxSymbolsPerShard,
        provider,
        resolution,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        name: name.trim() || null,
        options: {
          enabled: includeOptions,
          feed: optionsFeed,
        },
      })
      setConfirmOpen(false)
      setLaunchResult({
        status: 'success',
        message: 'Dataset launch submitted successfully.',
        datasetId: response.dataset_id,
      })
    } catch (err) {
      setConfirmOpen(false)
      setLaunchResult({
        status: 'failed',
        message: err instanceof Error ? err.message : 'Failed to create dataset',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleSampleFromUniverse = async () => {
    if (!selectedUniverse) {
      setError('Choose a universe before sampling symbols.')
      return
    }
    if (universeSymbols.length === 0) {
      setError('No universe symbols are loaded yet.')
      return
    }

    setSamplingUniverse(true)
    setError(null)
    try {
      const nextSymbols = sampleSymbols(universeSymbols, sampleSize)
      if (nextSymbols.length === 0) {
        throw new Error(`Universe ${selectedUniverse.key} does not have any symbols to sample.`)
      }
      setSampledSymbols(nextSymbols)
      setChosenSampleSymbols(nextSymbols)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sample universe symbols')
    } finally {
      setSamplingUniverse(false)
    }
  }

  const handleCloseSampleDialog = () => {
    if (chosenSampleSymbols.length > 0) {
      setSymbols((current) => normalizeSymbols([...current, ...chosenSampleSymbols]))
    }
    setSampleDialogOpen(false)
  }

  return (
    <Stack component="form" spacing={2.5} onSubmit={handleSubmit}>
      <Button component={RouterLink} to="/backtests/datasets" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
        Back to datasets
      </Button>

      {prefillLoading && prefillFromId && (
        <Alert severity="info">Loading dataset settings from {prefillFromId}…</Alert>
      )}
      {prefillError && (
        <Alert severity="warning">
          {prefillError}
          {prefillFromId ? ` Editing will continue with the default dataset settings.` : ''}
        </Alert>
      )}
      {prefillSourceId && !prefillLoading && (
        <Alert severity="info">
          Prefilled from dataset <strong>{prefillSourceId}</strong>. Edit any field before launching.
        </Alert>
      )}

      <Dialog
        open={launchResult !== null}
        onClose={() => setLaunchResult(null)}
        aria-labelledby="dataset-launch-result-title"
        aria-describedby="dataset-launch-result-description"
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
        <DialogTitle id="dataset-launch-result-title" sx={{ pb: 1 }}>
          {launchResult?.status === 'success' ? 'Dataset launched' : 'Dataset launch failed'}
        </DialogTitle>
        <DialogContent id="dataset-launch-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={launchResult?.status === 'success' ? 'success' : 'error'}>
              {launchResult?.message}
            </Alert>
            {launchResult?.status === 'success' && launchResult.datasetId && (
              <Typography color="text.secondary">
                You can open the new dataset from{' '}
                <Link component={RouterLink} to={`/backtests/datasets/${launchResult.datasetId}`}>
                  dataset {launchResult.datasetId}
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

      <Dialog
        open={sampleDialogOpen}
        onClose={handleCloseSampleDialog}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle sx={{ pb: 1 }}>Sample from universe</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Autocomplete
              options={availableUniverses}
              getOptionLabel={(option) => `${option.name} (${option.key})`}
              value={selectedUniverse}
              isOptionEqualToValue={(option, value) => option.key === value.key}
              onChange={(_event, value) => {
                setSelectedUniverseKey(value?.key ?? null)
                setSampledSymbols([])
                setChosenSampleSymbols([])
              }}
              loading={loadingUniverses}
              noOptionsText={loadingUniverses ? 'Loading universes…' : 'No universes are available yet.'}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Universe"
                  placeholder="Choose a universe"
                  helperText="Select a registry or user universe, then sample symbols from it."
                />
              )}
            />
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Typography variant="body2" sx={{ flex: 1 }}>
                  Sample size
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {universeSymbols.length > 0
                    ? `${sampleSize} / ${universeSymbols.length} symbols (${Math.round((sampleSize / universeSymbols.length) * 100)}%)`
                    : 'Loading…'}
                </Typography>
              </Stack>
              <Slider
                value={sampleSize}
                onChange={(_event, nextValue) => {
                  const next = Array.isArray(nextValue) ? nextValue[0] : nextValue
                  setSampleSize(next)
                }}
                min={1}
                max={Math.max(universeSymbols.length, 1)}
                step={1}
                disabled={loadingUniverseSymbols || universeSymbols.length === 0}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) =>
                  universeSymbols.length > 0
                    ? `${value} symbols (${Math.round((value / universeSymbols.length) * 100)}%)`
                    : `${value}`
                }
              />
              <Typography variant="caption" color="text.secondary">
                {universeSymbols.length > 0
                  ? 'Drag to choose how many symbols to sample from the universe.'
                  : 'Loading universe constituents…'}
              </Typography>
            </Stack>
            {sampledSymbols.length > 0 ? (
              <Stack spacing={1}>
                <Typography variant="body2" color="text.secondary">
                  Pick one or more sampled symbols. Closing the modal will add them to the dataset symbol basket.
                </Typography>
                <Autocomplete
                  multiple
                  options={sampledSymbols}
                  value={chosenSampleSymbols}
                  onChange={(_event, value) => setChosenSampleSymbols(normalizeSymbols(value))}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Sampled symbols"
                      placeholder="Choose one or more symbols"
                      helperText="Use chips to choose the dataset symbol from the sampled basket."
                    />
                  )}
                />
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {sampledSymbols.map((item) => {
                    const selected = chosenSampleSymbols.includes(item)
                    return (
                      <Chip
                        key={item}
                        label={item}
                        clickable
                        color={selected ? 'primary' : 'default'}
                        variant={selected ? 'filled' : 'outlined'}
                        onClick={() => {
                          setChosenSampleSymbols((current) =>
                            current.includes(item)
                              ? current.filter((value) => value !== item)
                              : [...current, item],
                          )
                        }}
                      />
                    )
                  })}
                </Box>
              </Stack>
            ) : (
              <Alert severity="info">
                Sample a universe to preview symbols. Closing the modal will add the chosen symbols to the dataset form.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={handleCloseSampleDialog} variant="outlined" color="inherit">
            Close
          </Button>
          <Button
            onClick={() => void handleSampleFromUniverse()}
            variant="contained"
            disabled={loadingUniverses || loadingUniverseSymbols || samplingUniverse || selectedUniverse === null}
          >
            {samplingUniverse ? 'Sampling…' : 'Sample symbols'}
          </Button>
          <Button
            onClick={() => {
              handleCloseSampleDialog()
            }}
            variant="contained"
            disabled={chosenSampleSymbols.length === 0}
          >
            Use selected
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        title="Launch dataset?"
        description={
          <Stack spacing={1.25}>
            <Typography color="text.secondary">
              This will submit an Argo workflow to build the dataset parquet and manifest files.
            </Typography>
            <Box
              sx={{
                px: 1.25,
                py: 1,
                borderRadius: 1,
                border: 1,
                borderColor: 'divider',
                bgcolor: 'action.hover',
              }}
            >
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.25 }}>
                {symbols.join(', ')} · {provider} · {resolution}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.25 }}>
                {startDate?.format('YYYY-MM-DD')} to {endDate?.format('YYYY-MM-DD')}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.25, display: 'block' }}>
                Max {maxSymbolsPerShard} symbols per shard
              </Typography>
            </Box>
          </Stack>
        }
        confirmLabel="Launch dataset"
        cancelLabel="Keep editing"
        intent="primary"
        loading={submitting}
        onCancel={() => {
          if (!submitting) {
            setConfirmOpen(false)
          }
        }}
        onConfirm={() => {
          void confirmSubmit()
        }}
      />

      <Stack spacing={0.5}>
        <Typography variant="h4">New Dataset</Typography>
        <Typography color="text.secondary">
          Launch a workflow that downloads bars and writes parquet into the configured storage root.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
          alignItems: 'start',
        }}
      >
        <Paper sx={{ p: 2.5, gridColumn: { md: '1 / -1' } }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Dataset details
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gap: 1.5,
                gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
              }}
            >
              <TextField
                fullWidth
                sx={fieldSx}
                label="Dataset name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                helperText="Optional friendly name shown in the dataset list."
              />
              <Autocomplete
                fullWidth
                multiple
                freeSolo
                options={platformSettings.backtest_defaults.symbols_seed_list}
                value={symbols}
                onChange={(_event, value) => setSymbols(normalizeSymbols(value))}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Symbols"
                    placeholder="Type a symbol and press Enter"
                    helperText="Type one or more symbols manually, or sample a basket from a universe."
                  />
                )}
              />
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-start', pt: 0.5 }}>
                <Button variant="outlined" onClick={() => setSampleDialogOpen(true)}>
                  Sample from universe
                </Button>
              </Box>
              <TextField
                fullWidth
                sx={fieldSx}
                select
                label="Provider"
                value={provider}
                onChange={(event) => setProvider(event.target.value as DatasetProvider)}
              >
                {PROVIDERS.map((item) => (
                  <MenuItem key={item} value={item}>
                    {item}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                fullWidth
                sx={fieldSx}
                select
                label="Resolution"
                value={resolution}
                onChange={(event) => setResolution(event.target.value as DatasetResolution)}
              >
                {RESOLUTIONS.map((item) => (
                  <MenuItem key={item} value={item}>
                    {item}
                  </MenuItem>
                ))}
              </TextField>
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
              <TextField
                fullWidth
                sx={fieldSx}
                label="Max symbols per shard"
                type="number"
                value={maxSymbolsPerShard}
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10)
                  setMaxSymbolsPerShard(Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_SYMBOLS_PER_SHARD)
                }}
                slotProps={{ htmlInput: { min: 1, step: 1 } }}
                helperText="Caps how many symbols a single worker downloads. Lower values reduce per-pod memory use."
              />
            </Box>
          </Stack>
        </Paper>

        <Paper
          variant="outlined"
          sx={{
            p: 2,
            bgcolor: 'action.hover',
            borderStyle: 'dashed',
            borderColor: 'divider',
          }}
        >
          <Stack spacing={1.25}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Options data
            </Typography>
            <FormControlLabel
              control={<Switch checked={includeOptions} onChange={(_, checked) => setIncludeOptions(checked)} />}
              label="Include options data"
            />
            <Typography variant="body2" color="text.secondary">
              Optional. When enabled, this launch also downloads Alpaca options bars for the same symbols and date range.
            </Typography>
            <TextField
              fullWidth
              sx={fieldSx}
              select
              label="Options feed"
              value={optionsFeed}
              disabled={!includeOptions}
              onChange={(event) => setOptionsFeed(event.target.value as DatasetOptionsFeed)}
              helperText="Indicative is the safest default; OPRA requires the matching subscription."
            >
              <MenuItem value="indicative">indicative</MenuItem>
              <MenuItem value="opra">opra</MenuItem>
            </TextField>
          </Stack>
        </Paper>

        <Paper
          sx={{
            p: 2,
            gridColumn: { md: '1 / -1' },
          }}
        >
          <Stack spacing={1.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Launch
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Review the launch details, then submit the workflow to generate the dataset files.
            </Typography>
            <Box sx={{ display: 'flex', justifyContent: 'flex-start' }}>
              <Button type="submit" variant="contained" disabled={submitting}>
                {submitting ? 'Launching…' : 'Launch dataset'}
              </Button>
            </Box>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}
