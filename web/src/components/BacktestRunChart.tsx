import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import {
  Alert,
  Box,
  CircularProgress,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'

import { fetchSymbolBars } from '../api/marketData'
import type { BacktestOrderRecord, BacktestTradeRecord } from '../types/backtests'
import type { MarketDataResponse, Resolution } from '../types/marketData'
import type { TradeChartFocusWindowMs } from '../utils/backtestChartFocus'
import { CandlestickChart, type ChartThemeMode } from './CandlestickChart'
import { ChartErrorBoundary } from './ChartErrorBoundary'

interface BacktestRunChartProps {
  symbol: string
  startDate: string
  endDate: string
  resolution: string
  orders: BacktestOrderRecord[]
  trades: BacktestTradeRecord[]
  focusWindow?: TradeChartFocusWindowMs | null
  onResetFocusWindow?: () => void
}

function computeNumDays(startDate: string, endDate: string): number {
  return dayjs(endDate).diff(dayjs(startDate), 'day') + 1
}

export function BacktestRunChart({
  symbol,
  startDate,
  endDate,
  resolution,
  orders,
  trades,
  focusWindow,
  onResetFocusWindow,
}: BacktestRunChartProps) {
  const theme = useTheme()
  const [data, setData] = useState<MarketDataResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [chartThemeMode, setChartThemeMode] = useState<ChartThemeMode>(
    theme.palette.mode === 'light' ? 'light' : 'dark',
  )

  useEffect(() => {
    let cancelled = false

    async function loadBars() {
      setLoading(true)
      setError(null)
      try {
        const numDays = computeNumDays(startDate, endDate)
        const response = await fetchSymbolBars({
          symbol,
          startDate,
          numDays,
          resolution: resolution as Resolution,
        })
        if (cancelled) {
          return
        }
        if (response.rows.length === 0) {
          setData(null)
          setError('No market bars available for this run period.')
          return
        }
        setData(response)
      } catch (err) {
        if (!cancelled) {
          setData(null)
          setError(err instanceof Error ? err.message : 'Failed to load chart data')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadBars()
    return () => {
      cancelled = true
    }
  }, [endDate, resolution, startDate, symbol])

  const loadingOverlayBg = chartThemeMode === 'dark' ? 'rgba(13, 17, 23, 0.6)' : 'rgba(255, 255, 255, 0.72)'

  return (
    <Stack spacing={1}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
      >
        <Typography variant="caption" color="text.secondary">
          Blue/orange arrows = orders · Green/red circles = closed trades (PnL)
        </Typography>

        <ToggleButtonGroup
          exclusive
          size="small"
          value={chartThemeMode}
          onChange={(_, nextValue: ChartThemeMode | null) => {
            if (nextValue) {
              setChartThemeMode(nextValue)
            }
          }}
          aria-label="Chart theme mode"
        >
          <Tooltip title="Light chart">
            <ToggleButton value="light" aria-label="Light chart">
              <LightModeIcon fontSize="small" />
            </ToggleButton>
          </Tooltip>
          <Tooltip title="Dark chart">
            <ToggleButton value="dark" aria-label="Dark chart">
              <DarkModeIcon fontSize="small" />
            </ToggleButton>
          </Tooltip>
        </ToggleButtonGroup>
      </Stack>

      <Box
        sx={{
          position: 'relative',
          minHeight: 440,
          height: { xs: 440, md: 480 },
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          overflow: 'hidden',
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
              bgcolor: loadingOverlayBg,
              zIndex: 1,
            }}
          >
            <CircularProgress size={32} />
          </Box>
        )}

        {error && !loading && (
          <Box sx={{ p: 2 }}>
            <Alert severity="warning">{error}</Alert>
          </Box>
        )}

        {!error && data && (
          <ChartErrorBoundary>
            <CandlestickChart
              data={data}
              orders={orders}
              trades={trades}
              focusWindow={focusWindow}
              onResetFocusWindow={onResetFocusWindow}
              showViewportWindow
              themeMode={chartThemeMode}
            />
          </ChartErrorBoundary>
        )}
      </Box>
    </Stack>
  )
}
