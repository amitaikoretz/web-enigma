import { LinearProgress, Paper, Stack, Typography } from '@mui/material'

interface BacktestProgressPanelProps {
  completedRuns: number
  totalRuns: number
}

export function BacktestProgressPanel({ completedRuns, totalRuns }: BacktestProgressPanelProps) {
  const progressValue = totalRuns === 0 ? 0 : (completedRuns / totalRuns) * 100

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Backtest in progress</Typography>
        <Typography color="text.secondary">
          {completedRuns} of {totalRuns} runs completed.
        </Typography>
        <LinearProgress
          variant={totalRuns === 0 ? 'indeterminate' : 'determinate'}
          value={progressValue}
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
