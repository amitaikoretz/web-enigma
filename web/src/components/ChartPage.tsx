import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import { useCallback, useState } from 'react'

import { runSingleDayBacktest } from '../api/dayBacktest'
import { fetchSymbolBars } from '../api/marketData'
import type { SingleDayBacktestResult } from '../types/dayBacktest'
import type { ChartQuery, MarketDataResponse, Resolution } from '../types/marketData'
import type { WorkspaceMode } from '../types/workspace'
import { CandlestickChart } from './CandlestickChart'
import { MarketDataForm } from './MarketDataForm'
import { StrategyParamsForm, type StrategySelection } from './StrategyParamsForm'

function toMarketDataResponse(
  symbol: string,
  resolution: string,
  date: string,
  cacheStatus: string,
  rows: MarketDataResponse['rows'],
): MarketDataResponse {
  return {
    symbol,
    provider: 'alpaca',
    resolution,
    start_date: date,
    stop_date: date,
    cache_status: cacheStatus,
    rows,
  }
}

function formatReturnPct(value: number | undefined): string {
  if (value === undefined) {
    return '—'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

export function ChartPage() {
  const [mode, setMode] = useState<WorkspaceMode>('browse')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [backtestError, setBacktestError] = useState<string | null>(null)
  const [data, setData] = useState<MarketDataResponse | null>(null)
  const [backtestResult, setBacktestResult] = useState<SingleDayBacktestResult | null>(null)
  const [strategySelection, setStrategySelection] = useState<StrategySelection>({
    strategy: '',
    strategyParams: {},
  })
  const [chartResolution, setChartResolution] = useState<Resolution>('1m')

  const handleStrategyChange = useCallback((selection: StrategySelection) => {
    setStrategySelection(selection)
  }, [])

  const handleModeChange = (_event: React.SyntheticEvent, nextMode: WorkspaceMode) => {
    setMode(nextMode)
    if (nextMode === 'browse') {
      setBacktestResult(null)
      setBacktestError(null)
    }
  }

  const handleBrowse = async (query: ChartQuery) => {
    setChartResolution(query.resolution)
    setLoading(true)
    setError(null)
    setBacktestError(null)
    setBacktestResult(null)
    try {
      const response = await fetchSymbolBars(query)
      if (response.rows.length === 0) {
        setData(null)
        setError('No bars returned for the selected range.')
        return
      }
      setData(response)
    } catch (err) {
      setData(null)
      setError(err instanceof Error ? err.message : 'Failed to load chart data')
    } finally {
      setLoading(false)
    }
  }

  const handleBacktest = async (query: ChartQuery) => {
    setChartResolution(query.resolution)
    if (!strategySelection.strategy) {
      setBacktestError('Select a strategy before running a backtest.')
      return
    }

    setLoading(true)
    setError(null)
    setBacktestError(null)
    try {
      const response = await runSingleDayBacktest({
        symbol: query.symbol,
        date: query.startDate,
        resolution: query.resolution,
        strategy: strategySelection.strategy,
        strategyParams: strategySelection.strategyParams,
      })

      if (response.bars.length === 0) {
        setData(null)
        setBacktestResult(null)
        setBacktestError('No bars returned for the selected day.')
        return
      }

      setData(
        toMarketDataResponse(
          response.symbol,
          response.resolution,
          response.date,
          response.cache_status,
          response.bars,
        ),
      )
      setBacktestResult(response.backtest)

      if (response.backtest.status === 'failed') {
        setBacktestError(response.backtest.error?.message ?? 'Backtest failed.')
      }
    } catch (err) {
      setBacktestResult(null)
      setBacktestError(err instanceof Error ? err.message : 'Failed to run backtest')
    } finally {
      setLoading(false)
    }
  }

  const summary = backtestResult?.summary
  const showBacktestStats = mode === 'backtest' && backtestResult

  return (
    <Stack spacing={3}>
      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Tabs
            value={mode}
            onChange={handleModeChange}
            aria-label="Chart workspace mode"
          >
            <Tab icon={<ShowChartIcon />} iconPosition="start" label="Browse" value="browse" />
            <Tab icon={<PlayArrowIcon />} iconPosition="start" label="Backtest" value="backtest" />
          </Tabs>

          <MarketDataForm
            mode={mode}
            loading={loading}
            onBrowse={handleBrowse}
            onBacktest={handleBacktest}
          />

          {mode === 'backtest' && (
            <StrategyParamsForm
              disabled={loading}
              resolution={chartResolution}
              onChange={handleStrategyChange}
            />
          )}

          {error && <Alert severity="error">{error}</Alert>}
          {backtestError && (
            <Alert severity={backtestResult ? 'warning' : 'error'}>{backtestError}</Alert>
          )}
        </Stack>
      </Paper>

      {data && (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Chip label={data.symbol} color="primary" variant="outlined" />
          <Chip label={data.resolution} variant="outlined" />
          <Chip label={`${data.start_date} → ${data.stop_date}`} variant="outlined" />
          <Chip label={`${data.rows.length} bars`} variant="outlined" />
          {showBacktestStats && summary && (
            <>
              <Chip
                label={`Return ${formatReturnPct(summary.return_pct)}`}
                color={summary.return_pct >= 0 ? 'success' : 'error'}
                variant="outlined"
              />
              <Chip label={`${summary.total_trades} trades`} variant="outlined" />
              <Chip label={`${summary.won_trades}W / ${summary.lost_trades}L`} variant="outlined" />
            </>
          )}
        </Stack>
      )}

      <Paper
        sx={{
          p: 1,
          position: 'relative',
          minHeight: 440,
          height: { xs: 440, md: 'calc(100vh - 280px)' },
        }}
      >
        {loading && (
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              bgcolor: 'rgba(13, 17, 23, 0.6)',
              zIndex: 1,
            }}
          >
            <CircularProgress />
          </Box>
        )}
        {!loading && !data && !error && !backtestError && (
          <Box
            sx={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Typography color="text.secondary">
              {mode === 'browse'
                ? 'Enter a symbol and click Load chart.'
                : 'Configure a strategy and click Run backtest.'}
            </Typography>
          </Box>
        )}
        {(data || loading) && (
          <CandlestickChart
            data={data}
            orders={mode === 'backtest' ? (backtestResult?.orders ?? []) : []}
            trades={mode === 'backtest' ? (backtestResult?.trades ?? []) : []}
          />
        )}
      </Paper>
    </Stack>
  )
}
