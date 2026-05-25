import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import {
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import type { ChartQuery, Resolution } from '../types/marketData'
import type { WorkspaceMode } from '../types/workspace'

const RESOLUTIONS: Resolution[] = ['1m', '5m', '15m', '1h', '1d']

interface MarketDataFormProps {
  mode: WorkspaceMode
  loading: boolean
  onBrowse: (query: ChartQuery) => void
  onBacktest: (query: ChartQuery) => void
}

export function MarketDataForm({ mode, loading, onBrowse, onBacktest }: MarketDataFormProps) {
  const [symbol, setSymbol] = useState('AAPL')
  const [startDate, setStartDate] = useState<Dayjs | null>(dayjs())
  const [numDays, setNumDays] = useState('1')
  const [resolution, setResolution] = useState<Resolution>('1m')

  const buildQuery = (): ChartQuery | null => {
    if (!startDate) {
      return null
    }
    const parsedNumDays = mode === 'backtest' ? 1 : Number(numDays)
    if (!Number.isFinite(parsedNumDays) || parsedNumDays < 1) {
      return null
    }
    return {
      symbol: symbol.trim().toUpperCase(),
      startDate: startDate.format('YYYY-MM-DD'),
      numDays: parsedNumDays,
      resolution,
    }
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const query = buildQuery()
    if (!query) {
      return
    }
    if (mode === 'browse') {
      onBrowse(query)
    } else {
      onBacktest(query)
    }
  }

  const isBrowse = mode === 'browse'

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'flex-end' } }}>
        <TextField
          label="Symbol"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          required
          size="small"
          sx={{ minWidth: 120 }}
        />
        <DatePicker
          label={isBrowse ? 'Start date' : 'Trading day'}
          value={startDate}
          onChange={setStartDate}
          slotProps={{ textField: { size: 'small', required: true } }}
        />
        {isBrowse && (
          <TextField
            label="Days"
            type="number"
            value={numDays}
            onChange={(event) => setNumDays(event.target.value)}
            slotProps={{ htmlInput: { min: 1 } }}
            required
            size="small"
            sx={{ minWidth: 100 }}
          />
        )}
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel id="resolution-label">Resolution</InputLabel>
          <Select
            labelId="resolution-label"
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
        <Button
          type="submit"
          variant="contained"
          startIcon={isBrowse ? <ShowChartIcon /> : <PlayArrowIcon />}
          disabled={loading || !startDate}
        >
          {isBrowse ? 'Load chart' : 'Run backtest'}
        </Button>
      </Stack>
    </Box>
  )
}
