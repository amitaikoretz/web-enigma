import { LinearProgress, Paper, Stack, Typography } from '@mui/material'

interface DataDownloadProgressPanelProps {
  completedRecords: number
  totalRecords: number
  successfulRecords: number
  failedRecords: number
}

export function DataDownloadProgressPanel({
  completedRecords,
  totalRecords,
  successfulRecords,
  failedRecords,
}: DataDownloadProgressPanelProps) {
  const progressValue = totalRecords === 0 ? 0 : (completedRecords / totalRecords) * 100

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Download in progress</Typography>
        <Typography color="text.secondary">
          {completedRecords} of {totalRecords} records processed
          {failedRecords > 0 ? ` (${failedRecords} failed so far)` : ''}.
        </Typography>
        {successfulRecords > 0 && (
          <Typography variant="body2" color="text.secondary">
            {successfulRecords} succeeded
          </Typography>
        )}
        <LinearProgress
          variant={totalRecords === 0 ? 'indeterminate' : 'determinate'}
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
