import type { DatasetJobStatus } from '../types/datasets'
import { StatusPill, titleCaseStatus } from './StatusPill'

type DatasetStatusTone = 'success' | 'error' | 'info' | 'warning'

function resolveDatasetStatusColor(status: DatasetJobStatus): DatasetStatusTone {
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

export function DatasetStatusChip({ status }: { status: DatasetJobStatus }) {
  return <StatusPill label={titleCaseStatus(status)} color={resolveDatasetStatusColor(status)} pulseDot={status === 'running'} />
}
