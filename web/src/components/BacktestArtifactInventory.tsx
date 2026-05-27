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

import type {
  BacktestArtifactEntry,
  BacktestArtifactRole,
  BacktestArtifactSummaryItem,
} from '../types/backtests'
import { resolveArtifactDescription } from '../utils/artifactDescriptions'
import { publicArtifacts } from './BacktestArtifactChips'
import { CollapsibleSection } from './CollapsibleSection'

type ArtifactInventoryItem = BacktestArtifactEntry | BacktestArtifactSummaryItem

const ROLE_LABELS: Record<BacktestArtifactRole, string> = {
  primary: 'Primary outputs',
  sidecar: 'Sidecar data',
  manifest: 'Sharding',
  shard: 'Shard files',
}

const ROLE_ORDER: BacktestArtifactRole[] = ['primary', 'sidecar']

function formatBytes(sizeBytes: number | null | undefined): string {
  if (sizeBytes === null || sizeBytes === undefined) {
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

function groupArtifacts(
  artifacts: ArtifactInventoryItem[],
): Array<[BacktestArtifactRole, ArtifactInventoryItem[]]> {
  const grouped = new Map<BacktestArtifactRole, ArtifactInventoryItem[]>()
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
  artifacts: ArtifactInventoryItem[]
  defaultExpanded?: boolean
}

export function BacktestArtifactInventory({
  artifacts,
  defaultExpanded = true,
}: BacktestArtifactInventoryProps) {
  const visibleArtifacts = publicArtifacts(artifacts)
  const groups = groupArtifacts(visibleArtifacts)

  return (
    <CollapsibleSection title="Auxiliary data files" defaultExpanded={defaultExpanded}>
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          Extra JSON and Parquet files written for this backtest. The report JSON is a slim summary;
          detailed run data lives in sidecar files when present.
        </Typography>

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
                    <TableCell>File</TableCell>
                    <TableCell>Contents</TableCell>
                    <TableCell>Format</TableCell>
                    <TableCell align="right">Size</TableCell>
                    <TableCell>Path</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((artifact) => (
                    <TableRow
                      key={'path' in artifact && artifact.path ? artifact.path : `${artifact.kind}:${artifact.label}`}
                      hover
                    >
                      <TableCell>{artifact.label}</TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {resolveArtifactDescription(artifact)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" label={formatChipLabel(artifact.format)} variant="outlined" />
                      </TableCell>
                      <TableCell align="right">
                        {formatBytes('size_bytes' in artifact ? artifact.size_bytes : null)}
                      </TableCell>
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
                          {'path' in artifact ? artifact.path : '—'}
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
