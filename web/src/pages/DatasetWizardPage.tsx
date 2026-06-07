import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  MenuItem,
  Paper,
  Switch,
  Stack,
  TextField,
  Typography,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
} from '@mui/material'
import type { SxProps, Theme } from '@mui/material/styles'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { createDataset } from '../api/datasets'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useSettings } from '../settings/useSettings'
import type { DatasetOptionsFeed, DatasetProvider, DatasetResolution } from '../types/datasets'
import { useNavigate } from 'react-router-dom'

const RESOLUTIONS: DatasetResolution[] = ['1m', '5m', '15m', '1h', '1d']
const PROVIDERS: DatasetProvider[] = ['alpaca', 'yahoo']

const fieldSx: SxProps<Theme> = { minWidth: 0 }

export function DatasetWizardPage() {
  const navigate = useNavigate()
  const { platformSettings } = useSettings()
  const [symbol, setSymbol] = useState(platformSettings.backtest_defaults.symbols_seed_list[0] ?? 'AAPL')
  const [name, setName] = useState('')
  const [provider, setProvider] = useState<DatasetProvider>('alpaca')
  const [resolution, setResolution] = useState<DatasetResolution>(platformSettings.backtest_defaults.resolution)
  const [includeOptions, setIncludeOptions] = useState(false)
  const [optionsFeed, setOptionsFeed] = useState<DatasetOptionsFeed>('indicative')
  const [startDate, setStartDate] = useState<Dayjs | null>(dayjs().subtract(30, 'day'))
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [error, setError] = useState<string | null>(null)
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
        symbol,
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
      navigate('/backtests/datasets', {
        replace: true,
        state: {
          launchResult: {
            status: 'success',
            message: 'Dataset launch submitted successfully.',
            datasetId: response.dataset_id,
          },
        },
      })
    } catch (err) {
      setConfirmOpen(false)
      setLaunchResult({
        status: 'failed',
        message: err instanceof Error ? err.message : 'Failed to create dataset',
      })
      navigate('/backtests/datasets', {
        replace: true,
        state: {
          launchResult: {
            status: 'failed',
            message: err instanceof Error ? err.message : 'Failed to create dataset',
          },
        },
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack component="form" spacing={2.5} onSubmit={handleSubmit}>
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
                {symbol} · {provider} · {resolution}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.25 }}>
                {startDate?.format('YYYY-MM-DD')} to {endDate?.format('YYYY-MM-DD')}
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
              <TextField
                fullWidth
                sx={fieldSx}
                label="Symbol"
                value={symbol}
                onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              />
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
              Optional. When enabled, this launch also downloads Alpaca options bars for the same symbol and date range.
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
