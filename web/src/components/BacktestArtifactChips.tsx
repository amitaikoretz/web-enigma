import { Chip, Stack, Typography } from '@mui/material'

import type {
  BacktestArtifactEntry,
  BacktestArtifactFormat,
  BacktestArtifactRole,
  BacktestArtifactSummaryItem,
} from '../types/backtests'

type ArtifactChipSource = Pick<
  BacktestArtifactEntry | BacktestArtifactSummaryItem,
  'kind' | 'label' | 'format' | 'role'
>

const ROLE_LABELS: Record<BacktestArtifactRole, string> = {
  primary: 'Primary',
  sidecar: 'Sidecar',
  manifest: 'Manifest',
  shard: 'Shard',
}

function formatChipLabel(format: BacktestArtifactFormat): string {
  if (format === 'parquet') {
    return 'Parquet'
  }
  return format.toUpperCase()
}

function chipColor(role: BacktestArtifactRole): 'default' | 'primary' | 'secondary' | 'info' {
  if (role === 'sidecar') {
    return 'primary'
  }
  if (role === 'manifest' || role === 'shard') {
    return 'secondary'
  }
  return 'default'
}

interface BacktestArtifactChipsProps {
  artifacts: ArtifactChipSource[]
  emptyLabel?: string
  maxChips?: number
}

export function BacktestArtifactChips({
  artifacts,
  emptyLabel = '—',
  maxChips,
}: BacktestArtifactChipsProps) {
  if (artifacts.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {emptyLabel}
      </Typography>
    )
  }

  const visible = maxChips ? artifacts.slice(0, maxChips) : artifacts
  const hiddenCount = maxChips ? Math.max(artifacts.length - maxChips, 0) : 0

  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
      {visible.map((artifact) => (
        <Chip
          key={`${artifact.kind}:${artifact.label}`}
          size="small"
          variant="outlined"
          color={chipColor(artifact.role)}
          label={`${artifact.label} · ${formatChipLabel(artifact.format)}`}
          title={`${ROLE_LABELS[artifact.role]} · ${artifact.kind}`}
        />
      ))}
      {hiddenCount > 0 && (
        <Chip size="small" variant="outlined" label={`+${hiddenCount} more`} />
      )}
    </Stack>
  )
}

export function sidecarArtifacts<T extends ArtifactChipSource>(artifacts: T[]): T[] {
  return artifacts.filter((artifact) => artifact.role === 'sidecar')
}
