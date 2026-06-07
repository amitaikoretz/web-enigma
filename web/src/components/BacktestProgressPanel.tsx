import { LinearProgress, Paper, Stack, Typography } from '@mui/material'

import { formatDurationMs } from '../utils/formatDuration'

interface BacktestProgressPanelProps {
  progressPct: number
  isIndeterminate?: boolean
  startedAt?: string | null
  title?: string
}

export function BacktestProgressPanel({
  progressPct,
  isIndeterminate = false,
  startedAt = null,
  title = 'Backtest in progress',
}: BacktestProgressPanelProps) {
  const nowMs = Date.now()
  const startMs = Date.parse(startedAt ?? '')
  const elapsedMs = Number.isNaN(startMs) ? null : Math.max(0, nowMs - startMs)

  const pct = Number.isFinite(progressPct) ? Math.max(0, Math.min(100, progressPct)) : 0
  const canEstimate = !isIndeterminate && elapsedMs !== null && pct > 0
  const estimatedTotalMs = canEstimate ? elapsedMs! / (pct / 100) : null
  const remainingMs =
    estimatedTotalMs !== null && elapsedMs !== null
      ? Math.max(0, Math.round(estimatedTotalMs - elapsedMs))
      : null

  const pctLabel = isIndeterminate ? '—' : `${pct.toFixed(1)}%`
  const elapsedLabel = elapsedMs === null ? '—' : formatDurationMs(elapsedMs)
  const remainingLabel = remainingMs === null ? '—' : formatDurationMs(remainingMs)

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{title}</Typography>
        <LinearProgress
          variant={isIndeterminate ? 'indeterminate' : 'determinate'}
          value={pct}
          color="primary"
          sx={{
            height: 10,
            borderRadius: 1,
            bgcolor: 'action.hover',
            '& .MuiLinearProgress-bar': {
              borderRadius: 1,
            },
          }}
        />
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={{ xs: 0.5, sm: 2 }}
          sx={{ justifyContent: 'space-between' }}
        >
          <Typography variant="body2" color="text.secondary">
            {pctLabel} complete
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Elapsed: {elapsedLabel}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            ETA: {remainingLabel}
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  )
}
