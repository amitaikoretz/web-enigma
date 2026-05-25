import { Chip } from '@mui/material'

import type { BacktestJobStatus, BacktestReportStatus } from '../types/backtests'

interface BacktestStatusChipProps {
  status: BacktestJobStatus
}

interface ReportStatusChipProps {
  status: BacktestReportStatus
}

export function BacktestStatusChip({ status }: BacktestStatusChipProps) {
  const color =
    status === 'completed'
      ? 'success'
      : status === 'failed'
        ? 'error'
        : status === 'running'
          ? 'info'
          : 'warning'

  return <Chip label={status.replace('_', ' ')} color={color} size="small" />
}

export function ReportStatusChip({ status }: ReportStatusChipProps) {
  const color =
    status === 'success' ? 'success' : status === 'partial_failure' ? 'warning' : 'error'

  return <Chip label={status.replace('_', ' ')} color={color} variant="outlined" size="small" />
}
