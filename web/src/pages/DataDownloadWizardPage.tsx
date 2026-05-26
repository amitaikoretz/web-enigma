import CloudDownloadIcon from '@mui/icons-material/CloudDownload'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createDataDownload } from '../api/dataDownloads'
import { fetchServerInfo } from '../api/serverInfo'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { useSettings } from '../settings/useSettings'
import type { DataDownloadFeed } from '../types/dataDownloads'
import type { BacktestFeed } from '../types/backtests'
import type { Resolution } from '../types/marketData'

const RESOLUTIONS: Resolution[] = ['1m', '5m', '15m', '1h', '1d']
const FEEDS: DataDownloadFeed[] = ['iex', 'sip', 'otc']

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

export function DataDownloadWizardPage() {
  const navigate = useNavigate()
  const { platformSettings } = useSettings()
  const [symbols, setSymbols] = useState<string[]>(platformSettings.backtest_defaults.symbols_seed_list)
  const [startDate, setStartDate] = useState<Dayjs | null>(
    resolveStartDatePreset(platformSettings.backtest_defaults.date_range_preset),
  )
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [resolution, setResolution] = useState<Resolution>(platformSettings.backtest_defaults.resolution)
  const [feed, setFeed] = useState<DataDownloadFeed>(platformSettings.backtest_defaults.feed)
  const [forceRefresh, setForceRefresh] = useState(false)
  const [outputFolder, setOutputFolder] = useState('')
  const [defaultCacheDir, setDefaultCacheDir] = useState<string | null>(null)
  const [loadingServerInfo, setLoadingServerInfo] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchServerInfo()
      .then((info) => {
        if (!cancelled) {
          setDefaultCacheDir(info.backtest_cache_dir)
          setOutputFolder(info.backtest_cache_dir)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load server info')
          setOutputFolder('.cache/backtest-data')
          setDefaultCacheDir('.cache/backtest-data')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingServerInfo(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const hasValidDateRange =
    startDate !== null && endDate !== null && !endDate.isBefore(startDate, 'day')
  const totalRecords = symbols.length
  const resolvedOutputFolder = outputFolder.trim() || defaultCacheDir || '.cache/backtest-data'

  const reviewSummary = useMemo(() => {
    if (!hasValidDateRange || symbols.length === 0) {
      return null
    }
    return `${symbols.length} symbol${symbols.length === 1 ? '' : 's'} · ${formatDateRange(startDate, endDate)} · ${resolution} · ${feed.toUpperCase()}`
  }, [symbols.length, hasValidDateRange, startDate, endDate, resolution, feed])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!startDate || !endDate || !hasValidDateRange) {
      setError('Choose a valid date range before submitting.')
      return
    }
    if (symbols.length === 0) {
      setError('Add at least one symbol before submitting.')
      return
    }

    if (platformSettings.platform_behavior.confirm_before_launch) {
      const confirmed = window.confirm(
        `Download market data for ${symbols.length} symbol${symbols.length === 1 ? '' : 's'}?`,
      )
      if (!confirmed) {
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      const response = await createDataDownload({
        output_folder: resolvedOutputFolder,
        records: symbols.map((symbol) => ({
          symbol,
          start_date: startDate.format('YYYY-MM-DD'),
          stop_date: endDate.format('YYYY-MM-DD'),
          resolution,
          feed,
          force_refresh: forceRefresh,
        })),
      })
      navigate(`/data/downloads/${response.job_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create data download job')
      setSubmitting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Download Market Data</Typography>
        <Typography color="text.secondary">
          Prefetch Alpaca OHLCV bars into the server parquet cache for a symbol basket.
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {loadingServerInfo && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <CircularProgress size={20} />
          <Typography color="text.secondary">Loading server cache settings…</Typography>
        </Stack>
      )}

      <Stack component="form" spacing={3} onSubmit={handleSubmit}>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Universe</Typography>
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
                  helperText="Each symbol becomes one download record for the selected date range."
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
                <InputLabel id="download-resolution-label">Resolution</InputLabel>
                <Select
                  labelId="download-resolution-label"
                  label="Resolution"
                  value={resolution}
                  onChange={(event) => setResolution(event.target.value as Resolution)}
                >
                  {RESOLUTIONS.map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel id="download-feed-label">Feed</InputLabel>
                <Select
                  labelId="download-feed-label"
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
            <FormControlLabel
              control={
                <Switch
                  checked={forceRefresh}
                  onChange={(event) => setForceRefresh(event.target.checked)}
                />
              }
              label="Force refresh (ignore existing cache entries)"
            />
          </Stack>
        </Paper>

        <CollapsibleSection
          title="Advanced"
          subtitle={`Default cache: ${defaultCacheDir ?? 'loading…'}`}
        >
          <TextField
            fullWidth
            label="Output folder"
            value={outputFolder}
            onChange={(event) => setOutputFolder(event.target.value)}
            helperText="Must be under the server cache root. Parquet files are written using the standard cache layout."
            slotProps={{
              input: {
                sx: { fontFamily: 'monospace' },
              },
            }}
          />
        </CollapsibleSection>

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
            {reviewSummary ? (
              <Typography color="text.secondary">{reviewSummary}</Typography>
            ) : (
              <Typography color="text.secondary">{formatDateRange(startDate, endDate)}</Typography>
            )}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
              <Box>
                <Typography variant="overline">Symbols</Typography>
                <Typography variant="h5">{symbols.length}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Parquet files</Typography>
                <Typography variant="h5">{totalRecords}</Typography>
              </Box>
              <Box>
                <Typography variant="overline">Destination</Typography>
                <Typography variant="body1" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                  {resolvedOutputFolder}
                </Typography>
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
                startIcon={<CloudDownloadIcon />}
                disabled={
                  submitting ||
                  loadingServerInfo ||
                  !hasValidDateRange ||
                  symbols.length === 0
                }
              >
                {submitting ? 'Submitting…' : 'Download data'}
              </Button>
            </Box>
          </Stack>
        </Paper>
      </Stack>
    </Stack>
  )
}
