import { Chip } from '@mui/material'

import type { DataDownloadJobStatus } from '../types/dataDownloads'

interface DataDownloadStatusChipProps {
  status: DataDownloadJobStatus
}

export function DataDownloadStatusChip({ status }: DataDownloadStatusChipProps) {
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

interface CacheStatusChipProps {
  cacheStatus: string | null
  failed?: boolean
}

export function CacheStatusChip({ cacheStatus, failed = false }: CacheStatusChipProps) {
  if (failed) {
    return <Chip label="Failed" color="error" size="small" variant="outlined" />
  }

  const label =
    cacheStatus === 'hit'
      ? 'Cached'
      : cacheStatus === 'miss'
        ? 'Downloaded'
        : cacheStatus === 'stale_refetch'
          ? 'Refreshed'
          : cacheStatus === 'force_refresh'
            ? 'Forced refresh'
            : cacheStatus ?? 'Unknown'

  const color =
    cacheStatus === 'hit'
      ? 'success'
      : cacheStatus === 'force_refresh'
        ? 'warning'
        : 'info'

  return <Chip label={label} color={color} size="small" variant="outlined" />
}
