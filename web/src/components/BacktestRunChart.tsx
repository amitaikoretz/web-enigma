import { Alert, Box, CircularProgress, Stack, Typography } from '@mui/material'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'

import { fetchSymbolBars } from '../api/marketData'
import type { BacktestOrderRecord, BacktestTradeRecord } from '../types/backtests'
import type { MarketDataResponse, Resolution } from '../types/marketData'
import { CandlestickChart } from './CandlestickChart'
import { ChartErrorBoundary } from './ChartErrorBoundary'

interface BacktestRunChartProps {
  symbol: string
  startDate: string
  endDate: string
  resolution: string
  orders: BacktestOrderRecord[]
  trades: BacktestTradeRecord[]
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
}: BacktestRunChartProps) {
  const [data, setData] = useState<MarketDataResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        Blue/orange arrows = orders · Green/red circles = closed trades (PnL)
      </Typography>

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
              bgcolor: 'rgba(13, 17, 23, 0.6)',
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
              showViewportWindow
            />
          </ChartErrorBoundary>
        )}
      </Box>
    </Stack>
  )
}
