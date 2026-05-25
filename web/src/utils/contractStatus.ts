import type { ContractLifecycleStatus, TradingContract } from '../types/tradingContracts'

export function resolveContractStatus(
  contract: Pick<TradingContract, 'start_datetime' | 'end_datetime'>,
  now = new Date(),
): ContractLifecycleStatus {
  const start = new Date(contract.start_datetime)
  const end = new Date(contract.end_datetime)
  const timestamp = now.valueOf()

  if (timestamp < start.valueOf()) {
    return 'upcoming'
  }
  if (timestamp >= end.valueOf()) {
    return 'expired'
  }
  return 'active'
}
