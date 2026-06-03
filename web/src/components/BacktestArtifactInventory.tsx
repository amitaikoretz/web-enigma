import {
  Chip,
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
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { useEffect, useRef, useState } from 'react'

import type {
  BacktestArtifactEntry,
  BacktestArtifactRole,
  BacktestArtifactSummaryItem,
} from '../types/backtests'
import { resolveArtifactDescription } from '../utils/artifactDescriptions'
import { buildSidecarCopySnippet } from '../utils/backtestArtifactCopy'
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
  const [copiedArtifactKey, setCopiedArtifactKey] = useState<string | null>(null)
  const copyResetTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current)
      }
    }
  }, [])

  async function handleCopyCode(artifact: ArtifactInventoryItem, artifactKey: string) {
    try {
      await navigator.clipboard.writeText(buildSidecarCopySnippet(artifact))
      setCopiedArtifactKey(artifactKey)
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current)
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedArtifactKey(null)
        copyResetTimerRef.current = null
      }, 1500)
    } catch {
      // Clipboard access may be unavailable in some environments.
    }
  }

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
                        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
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
                          {artifact.role === 'sidecar' && (
                            <Tooltip
                              title={
                                copiedArtifactKey ===
                                ('path' in artifact && artifact.path ? artifact.path : `${artifact.kind}:${artifact.label}`)
                                  ? 'Copied'
                                  : 'Copy Python snippet'
                              }
                            >
                              <span>
                                <IconButton
                                  size="small"
                                  aria-label={
                                    copiedArtifactKey ===
                                    ('path' in artifact && artifact.path ? artifact.path : `${artifact.kind}:${artifact.label}`)
                                      ? 'Copied Python snippet'
                                      : 'Copy Python snippet'
                                  }
                                  sx={{ p: 0.25 }}
                                  onClick={() => {
                                    void handleCopyCode(
                                      artifact,
                                      'path' in artifact && artifact.path ? artifact.path : `${artifact.kind}:${artifact.label}`,
                                    )
                                  }}
                                >
                                  <ContentCopyIcon fontSize="inherit" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                        </Stack>
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
