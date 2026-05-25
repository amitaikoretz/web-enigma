import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material'
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useCallback, useState } from 'react'

import { updateTradingContract } from '../api/tradingContracts'
import type { TradingContract } from '../types/tradingContracts'
import { StrategyParamsForm, type StrategySelection } from './StrategyParamsForm'

function toTimezoneAwareIso(value: Dayjs | null): string | null {
  if (!value || !value.isValid()) {
    return null
  }
  return value.format('YYYY-MM-DDTHH:mm:ssZ')
}

interface ContractEditDialogProps {
  contract: TradingContract | null
  open: boolean
  onClose: () => void
  onUpdated: () => void
}

export function ContractEditDialog({ contract, open, onClose, onUpdated }: ContractEditDialogProps) {
  const [symbol, setSymbol] = useState('')
  const [strategySelection, setStrategySelection] = useState<StrategySelection | null>(null)
  const [startDatetime, setStartDatetime] = useState<Dayjs | null>(null)
  const [endDatetime, setEndDatetime] = useState<Dayjs | null>(null)
  const [maximumTradeSize, setMaximumTradeSize] = useState('')
  const [totalInvested, setTotalInvested] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetFromContract = useCallback((nextContract: TradingContract) => {
    setSymbol(nextContract.symbol)
    setStrategySelection({
      strategy: nextContract.strategy,
      strategyParams: nextContract.strategy_params,
    })
    setStartDatetime(dayjs(nextContract.start_datetime))
    setEndDatetime(dayjs(nextContract.end_datetime))
    setMaximumTradeSize(String(nextContract.maximum_trade_size))
    setTotalInvested(String(nextContract.total_invested))
    setError(null)
  }, [])

  const handleEntered = () => {
    if (contract) {
      resetFromContract(contract)
    }
  }

  const handleStrategyChange = useCallback((selection: StrategySelection) => {
    setStrategySelection(selection)
  }, [])

  async function handleSubmit() {
    if (!contract) {
      return
    }
    setError(null)

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
      await updateTradingContract(contract.id, {
        symbol: normalizedSymbol,
        strategy: strategySelection.strategy,
        strategy_params: strategySelection.strategyParams,
        start_datetime: startIso,
        end_datetime: endIso,
        maximum_trade_size: parsedMaximumTradeSize,
        total_invested: parsedTotalInvested,
      })
      onUpdated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update trading contract')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={submitting ? undefined : onClose}
      fullWidth
      maxWidth="md"
      slotProps={{
        transition: {
          onEntered: handleEntered,
        },
      }}
    >
      <DialogTitle>Edit contract</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}

          <TextField
            label="Symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            disabled={submitting}
            required
            fullWidth
            size="small"
          />

          {contract && (
            <StrategyParamsForm
              key={`${contract.id}-${contract.revision}`}
              disabled={submitting}
              resolution="1d"
              initialSelection={{
                strategy: contract.strategy,
                strategyParams: contract.strategy_params,
              }}
              onChange={handleStrategyChange}
            />
          )}

          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            <DateTimePicker
              label="Start datetime"
              value={startDatetime}
              onChange={setStartDatetime}
              disabled={submitting}
              slotProps={{ textField: { size: 'small', fullWidth: true, required: true } }}
            />
            <DateTimePicker
              label="End datetime"
              value={endDatetime}
              onChange={setEndDatetime}
              disabled={submitting}
              slotProps={{ textField: { size: 'small', fullWidth: true, required: true } }}
            />
            <TextField
              label="Maximum trade size"
              type="number"
              value={maximumTradeSize}
              onChange={(event) => setMaximumTradeSize(event.target.value)}
              disabled={submitting}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="Total invested"
              type="number"
              value={totalInvested}
              onChange={(event) => setTotalInvested(event.target.value)}
              disabled={submitting}
              required
              fullWidth
              size="small"
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleSubmit()}
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <SaveOutlinedIcon />}
        >
          Save changes
        </Button>
      </DialogActions>
    </Dialog>
  )
}
