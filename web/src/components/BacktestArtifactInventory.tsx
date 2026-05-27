import {
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'

import type { BacktestArtifactEntry, BacktestArtifactRole } from '../types/backtests'
import { BacktestArtifactChips } from './BacktestArtifactChips'
import { CollapsibleSection } from './CollapsibleSection'

const ROLE_LABELS: Record<BacktestArtifactRole, string> = {
  primary: 'Primary outputs',
  sidecar: 'Sidecar data',
  manifest: 'Sharding',
  shard: 'Shard files',
}

const ROLE_ORDER: BacktestArtifactRole[] = ['primary', 'manifest', 'sidecar', 'shard']

function formatBytes(sizeBytes: number | null): string {
  if (sizeBytes === null) {
    return '—'
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatChipLabel(format: BacktestArtifactEntry['format']): string {
  if (format === 'parquet') {
    return 'Parquet'
  }
  return format.toUpperCase()
}

function groupArtifacts(artifacts: BacktestArtifactEntry[]): Array<[BacktestArtifactRole, BacktestArtifactEntry[]]> {
  const grouped = new Map<BacktestArtifactRole, BacktestArtifactEntry[]>()
  for (const artifact of artifacts) {
    const bucket = grouped.get(artifact.role) ?? []
    bucket.push(artifact)
    grouped.set(artifact.role, bucket)
  }
  return ROLE_ORDER.flatMap((role) => {
    const items = grouped.get(role)
    return items && items.length > 0 ? [[role, items] as const] : []
  })
}

interface BacktestArtifactInventoryProps {
  artifacts: BacktestArtifactEntry[]
  defaultExpanded?: boolean
}

export function BacktestArtifactInventory({
  artifacts,
  defaultExpanded = true,
}: BacktestArtifactInventoryProps) {
  const groups = groupArtifacts(artifacts)

  return (
    <CollapsibleSection title="Auxiliary data files" defaultExpanded={defaultExpanded}>
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          Extra JSON and Parquet files written for this backtest. The report JSON is a slim summary;
          detailed run data lives in sidecar files when present.
        </Typography>

        {artifacts.length > 0 && <BacktestArtifactChips artifacts={artifacts} />}

        {groups.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No artifact files are available yet.
          </Typography>
        ) : (
          groups.map(([role, items]) => (
            <Stack key={role} spacing={1}>
              <Typography variant="subtitle2">{ROLE_LABELS[role]}</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Data</TableCell>
                    <TableCell>Format</TableCell>
                    <TableCell align="right">Size</TableCell>
                    <TableCell>Path</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((artifact) => (
                    <TableRow key={artifact.path} hover>
                      <TableCell>{artifact.label}</TableCell>
                      <TableCell>
                        <Chip size="small" label={formatChipLabel(artifact.format)} variant="outlined" />
                      </TableCell>
                      <TableCell align="right">{formatBytes(artifact.size_bytes)}</TableCell>
                      <TableCell>
                        <Typography
                          component="code"
                          variant="body2"
                          sx={{
                            display: 'block',
                            fontFamily: 'monospace',
                            fontSize: '0.78rem',
                            wordBreak: 'break-all',
                          }}
                        >
                          {artifact.path}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ))
        )}
      </Stack>
    </CollapsibleSection>
  )
}
