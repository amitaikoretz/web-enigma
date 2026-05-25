import { Chip } from '@mui/material'

import type { WorkerEventSeverity } from '../types/liveRuntime'

interface RuntimeEventSeverityChipProps {
  severity: WorkerEventSeverity | string
}

export function RuntimeEventSeverityChip({ severity }: RuntimeEventSeverityChipProps) {
  const normalized = severity.toLowerCase()
  const color =
    normalized === 'error' ? 'error' : normalized === 'warn' || normalized === 'warning' ? 'warning' : 'default'

  return <Chip label={severity} color={color} size="small" variant="outlined" />
}
