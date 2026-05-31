import { LinearProgress, Paper, Stack, Typography } from '@mui/material'

interface BacktestProgressPanelProps {
  progressPct: number
  isIndeterminate?: boolean
}

export function BacktestProgressPanel({
  progressPct,
  isIndeterminate = false,
}: BacktestProgressPanelProps) {
  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Backtest in progress</Typography>
        <LinearProgress
          variant={isIndeterminate ? 'indeterminate' : 'determinate'}
          value={progressPct}
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
      </Stack>
    </Paper>
  )
}
