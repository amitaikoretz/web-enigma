import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import {
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import { useState } from 'react'

import { CacheStatusChip } from './DataDownloadStatusChip'
import type { DataDownloadRecordResult } from '../types/dataDownloads'

interface DownloadRecordsTableProps {
  records: DataDownloadRecordResult[]
  showPaths?: boolean
}

export function DownloadRecordsTable({ records, showPaths = false }: DownloadRecordsTableProps) {
  const [copiedPath, setCopiedPath] = useState<string | null>(null)

  async function copyPath(path: string) {
    try {
      await navigator.clipboard.writeText(path)
      setCopiedPath(path)
      window.setTimeout(() => setCopiedPath(null), 1500)
    } catch {
      // Clipboard access may be unavailable.
    }
  }

  if (records.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ py: 2 }}>
        No record results yet.
      </Typography>
    )
  }

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Symbol</TableCell>
          <TableCell>Range</TableCell>
          <TableCell>Resolution</TableCell>
          <TableCell>Feed</TableCell>
          <TableCell>Status</TableCell>
          <TableCell align="right">Rows</TableCell>
          {showPaths && <TableCell>Path</TableCell>}
          <TableCell>Notes</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {records.map((record) => {
          const failed = Boolean(record.error)
          const rowKey = `${record.symbol}-${record.start_date}-${record.stop_date}-${record.feed}`

          return (
            <TableRow key={rowKey}>
              <TableCell>{record.symbol}</TableCell>
              <TableCell>
                {record.start_date} → {record.stop_date}
              </TableCell>
              <TableCell>{record.resolution}</TableCell>
              <TableCell>{record.feed}</TableCell>
              <TableCell>
                <CacheStatusChip cacheStatus={record.cache_status} failed={failed} />
              </TableCell>
              <TableCell align="right">{record.row_count ?? '—'}</TableCell>
              {showPaths && (
                <TableCell sx={{ maxWidth: 280 }}>
                  {record.parquet_path ? (
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                      <Typography
                        variant="caption"
                        sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                      >
                        {record.parquet_path}
                      </Typography>
                      <Tooltip title={copiedPath === record.parquet_path ? 'Copied' : 'Copy path'}>
                        <IconButton
                          size="small"
                          aria-label="Copy parquet path"
                          onClick={() => {
                            void copyPath(record.parquet_path!)
                          }}
                        >
                          <ContentCopyIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  ) : (
                    '—'
                  )}
                </TableCell>
              )}
              <TableCell sx={{ maxWidth: 320 }}>
                {record.error ? (
                  <Typography variant="body2" color="error">
                    {record.error}
                  </Typography>
                ) : (
                  '—'
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
