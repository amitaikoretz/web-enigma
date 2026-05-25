import { Box, Paper, Stack, Typography } from '@mui/material'

import type { HistogramBin, TradeDistribution } from '../types/backtests'
import { formatMetricNumber } from './BacktestMetricGrid'

interface TradeDistributionChartsProps {
  distributions: TradeDistribution | null | undefined
  medianHoldMinutes: number | null | undefined
  medianSize: number | null | undefined
}

function formatBinLabel(bin: HistogramBin): string {
  return bin.label ?? `${bin.start}–${bin.end}`
}

function HistogramCard({
  title,
  bins,
  emptyMessage,
  accentColor,
}: {
  title: string
  bins: HistogramBin[]
  emptyMessage: string
  accentColor: string
}) {
  const total = bins.reduce((sum, bin) => sum + bin.count, 0)

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        flex: 1,
        minWidth: 0,
        bgcolor: 'background.default',
        height: '100%',
      }}
    >
      <Stack
        direction="row"
        sx={{ mb: 1.5, alignItems: 'baseline', justifyContent: 'space-between' }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {total} trade{total === 1 ? '' : 's'}
        </Typography>
      </Stack>

      {total === 0 ? (
        <Typography color="text.secondary" variant="body2">
          {emptyMessage}
        </Typography>
      ) : (
        <Stack spacing={1.25}>
          {bins.map((bin) => {
            const maxCount = Math.max(...bins.map((entry) => entry.count), 1)
            const widthPct = (bin.count / maxCount) * 100
            return (
              <Box
                key={`${bin.start}-${bin.end}-${bin.label ?? ''}`}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '88px 1fr 28px',
                  gap: 1,
                  alignItems: 'center',
                }}
              >
                <Typography variant="caption" color="text.secondary" noWrap title={formatBinLabel(bin)}>
                  {formatBinLabel(bin)}
                </Typography>
                <Box
                  sx={{
                    height: 20,
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    overflow: 'hidden',
                  }}
                >
                  <Box
                    sx={{
                      width: `${widthPct}%`,
                      minWidth: bin.count > 0 ? 10 : 0,
                      height: '100%',
                      bgcolor: accentColor,
                      transition: 'width 0.2s ease',
                    }}
                  />
                </Box>
                <Typography variant="caption" sx={{ textAlign: 'right', fontWeight: 600 }}>
                  {bin.count}
                </Typography>
              </Box>
            )
          })}
        </Stack>
      )}
    </Paper>
  )
}

export function TradeDistributionCharts({
  distributions,
  medianHoldMinutes,
  medianSize,
}: TradeDistributionChartsProps) {
  if (!distributions) {
    return (
      <Typography color="text.secondary" variant="body2">
        No distribution data available for this run.
      </Typography>
    )
  }

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Trade distributions
      </Typography>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        sx={{ alignItems: 'stretch' }}
      >
        <HistogramCard
          title="Hold time"
          bins={distributions.hold_time_bins}
          emptyMessage="No closed trades with hold-time data."
          accentColor="primary.main"
        />
        <HistogramCard
          title="Trade size (shares)"
          bins={distributions.size_bins}
          emptyMessage="No trade size data."
          accentColor="secondary.main"
        />
      </Stack>

      {(medianHoldMinutes != null || medianSize != null) && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {medianHoldMinutes != null && (
            <Typography variant="body2" color="text.secondary">
              Median hold: <strong>{formatMetricNumber(medianHoldMinutes, 1)} min</strong>
            </Typography>
          )}
          {medianSize != null && (
            <Typography variant="body2" color="text.secondary">
              Median size: <strong>{formatMetricNumber(medianSize, 2)} shares</strong>
            </Typography>
          )}
        </Stack>
      )}
    </Stack>
  )
}
