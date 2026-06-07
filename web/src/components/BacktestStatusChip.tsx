import type { BacktestJobStatus, BacktestReportStatus } from '../types/backtests'
import { StatusPill, titleCaseStatus } from './StatusPill'

type StatusTone = 'success' | 'error' | 'info' | 'warning'

interface BacktestStatusChipProps {
  status: BacktestJobStatus
}

interface ReportStatusChipProps {
  status: BacktestReportStatus
}

function resolveJobStatusColor(status: BacktestJobStatus): StatusTone {
  if (status === 'completed') {
    return 'success'
  }
  if (status === 'failed') {
    return 'error'
  }
  if (status === 'running') {
    return 'info'
  }
  return 'warning'
}

function resolveReportStatusColor(status: BacktestReportStatus): StatusTone {
  if (status === 'success') {
    return 'success'
  }
  if (status === 'partial_failure') {
    return 'warning'
  }
  return 'error'
}

export function BacktestStatusChip({ status }: BacktestStatusChipProps) {
  return (
    <StatusPill
      label={titleCaseStatus(status)}
      color={resolveJobStatusColor(status)}
      pulseDot={status === 'running'}
    />
  )
}

export function ReportStatusChip({ status }: ReportStatusChipProps) {
  return (
    <StatusPill
      label={titleCaseStatus(status)}
      color={resolveReportStatusColor(status)}
    />
  )
}
