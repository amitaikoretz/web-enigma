import { Chip } from '@mui/material'

import type { ContractLifecycleStatus } from '../types/tradingContracts'

interface ContractStatusChipProps {
  status: ContractLifecycleStatus
}

export function ContractStatusChip({ status }: ContractStatusChipProps) {
  const color =
    status === 'active' ? 'success' : status === 'upcoming' ? 'info' : 'default'

  return <Chip label={status} color={color} size="small" />
}
