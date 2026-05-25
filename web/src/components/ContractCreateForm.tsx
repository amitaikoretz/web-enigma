import AddIcon from '@mui/icons-material/Add'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useCallback, useState } from 'react'

import { createTradingContract } from '../api/tradingContracts'
import { StrategyParamsForm, type StrategySelection } from './StrategyParamsForm'

function toTimezoneAwareIso(value: Dayjs | null): string | null {
  if (!value || !value.isValid()) {
    return null
  }
  return value.format('YYYY-MM-DDTHH:mm:ssZ')
}

interface ContractCreateFormProps {
  disabled?: boolean
  onCreated: () => void
}

export function ContractCreateForm({ disabled = false, onCreated }: ContractCreateFormProps) {
  const [symbol, setSymbol] = useState('')
  const [strategySelection, setStrategySelection] = useState<StrategySelection | null>(null)
  const [startDatetime, setStartDatetime] = useState<Dayjs | null>(dayjs())
  const [endDatetime, setEndDatetime] = useState<Dayjs | null>(dayjs().add(7, 'day'))
  const [maximumTradeSize, setMaximumTradeSize] = useState('1000')
  const [totalInvested, setTotalInvested] = useState('2500')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleStrategyChange = useCallback((selection: StrategySelection) => {
    setStrategySelection(selection)
  }, [])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setSuccessMessage(null)

    const normalizedSymbol = symbol.trim().toUpperCase()
    if (!normalizedSymbol) {
      setError('Symbol is required.')
      return
    }
    if (!strategySelection) {
      setError('Strategy is required.')
      return
    }

    const startIso = toTimezoneAwareIso(startDatetime)
    const endIso = toTimezoneAwareIso(endDatetime)
    if (!startIso || !endIso) {
      setError('Start and end datetimes are required.')
      return
    }
    if (startDatetime && endDatetime && !startDatetime.isBefore(endDatetime)) {
      setError('Start datetime must be before end datetime.')
      return
    }

    const parsedMaximumTradeSize = Number(maximumTradeSize)
    const parsedTotalInvested = Number(totalInvested)
    if (!Number.isFinite(parsedMaximumTradeSize) || parsedMaximumTradeSize <= 0) {
      setError('Maximum trade size must be greater than 0.')
      return
    }
    if (!Number.isFinite(parsedTotalInvested) || parsedTotalInvested < 0) {
      setError('Total invested must be zero or greater.')
      return
    }

    setSubmitting(true)
    try {
      await createTradingContract({
        symbol: normalizedSymbol,
        strategy: strategySelection.strategy,
        strategy_params: strategySelection.strategyParams,
        start_datetime: startIso,
        end_datetime: endIso,
        maximum_trade_size: parsedMaximumTradeSize,
        total_invested: parsedTotalInvested,
      })
      setSuccessMessage(`Created contract for ${normalizedSymbol}.`)
      setSymbol('')
      setMaximumTradeSize('1000')
      setTotalInvested('2500')
      setStartDatetime(dayjs())
      setEndDatetime(dayjs().add(7, 'day'))
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create trading contract')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={3} component="form" onSubmit={(event) => void handleSubmit(event)}>
        <Stack spacing={0.5}>
          <Typography variant="h6">New contract</Typography>
          <Typography color="text.secondary" variant="body2">
            Define a live trading mandate with strategy, schedule, and risk limits.
          </Typography>
        </Stack>

        {error && <Alert severity="error">{error}</Alert>}
        {successMessage && <Alert severity="success">{successMessage}</Alert>}

        <TextField
          label="Symbol"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          disabled={disabled || submitting}
          required
          fullWidth
          size="small"
        />

        <StrategyParamsForm
          disabled={disabled || submitting}
          resolution="1d"
          onChange={handleStrategyChange}
        />

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          <DateTimePicker
            label="Start datetime"
            value={startDatetime}
            onChange={setStartDatetime}
            disabled={disabled || submitting}
            slotProps={{ textField: { size: 'small', fullWidth: true, required: true } }}
          />
          <DateTimePicker
            label="End datetime"
            value={endDatetime}
            onChange={setEndDatetime}
            disabled={disabled || submitting}
            slotProps={{ textField: { size: 'small', fullWidth: true, required: true } }}
          />
          <TextField
            label="Maximum trade size"
            type="number"
            value={maximumTradeSize}
            onChange={(event) => setMaximumTradeSize(event.target.value)}
            disabled={disabled || submitting}
            required
            fullWidth
            size="small"
            slotProps={{ htmlInput: { min: 0, step: 'any' } }}
          />
          <TextField
            label="Total invested"
            type="number"
            value={totalInvested}
            onChange={(event) => setTotalInvested(event.target.value)}
            disabled={disabled || submitting}
            required
            fullWidth
            size="small"
            slotProps={{ htmlInput: { min: 0, step: 'any' } }}
          />
        </Box>

        <Box>
          <Button
            type="submit"
            variant="contained"
            startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <AddIcon />}
            disabled={disabled || submitting}
          >
            Create contract
          </Button>
        </Box>
      </Stack>
    </Paper>
  )
}
