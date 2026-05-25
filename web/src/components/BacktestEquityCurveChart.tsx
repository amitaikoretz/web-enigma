import { Box, Typography } from '@mui/material'

import type { EquityPoint } from '../types/backtests'

interface BacktestEquityCurveChartProps {
  curve: EquityPoint[]
  title?: string
  height?: number
}

export function BacktestEquityCurveChart({
  curve,
  title = 'Equity curve',
  height = 220,
}: BacktestEquityCurveChartProps) {
  if (curve.length === 0) {
    return (
      <Box
        sx={{
          height,
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: 'action.hover',
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No equity curve data available.
        </Typography>
      </Box>
    )
  }

  const values = curve.map((point) => point.value)
  const minValue = Math.min(...values)
  const maxValue = Math.max(...values)
  const range = maxValue - minValue || 1
  const width = 960
  const padding = 24

  const points = curve
    .map((point, index) => {
      const x = padding + (index / Math.max(curve.length - 1, 1)) * (width - padding * 2)
      const y = padding + (1 - (point.value - minValue) / range) * (height - padding * 2)
      return `${x},${y}`
    })
    .join(' ')

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
        {title}
      </Typography>
      <Box sx={{ width: '100%', overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={title}>
          <rect x={0} y={0} width={width} height={height} fill="transparent" />
          <polyline
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            points={points}
            style={{ color: 'var(--mui-palette-primary-main, #1976d2)' }}
          />
        </svg>
      </Box>
    </Box>
  )
}
