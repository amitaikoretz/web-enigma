import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { Alert, Box, Button, Stack, Tooltip, Typography } from '@mui/material'
import { useMemo, useState } from 'react'

import type { BacktestArtifactEntry } from '../types/backtests'
import { CollapsibleSection } from './CollapsibleSection'

function buildCommands(outputPath: string | null, artifacts: BacktestArtifactEntry[]): string {
  const jsonPath = outputPath ?? '/path/to/backtest-report.json'

  const sidecars = artifacts.filter((artifact) => artifact.role === 'sidecar')
  const sidecarPaths = sidecars.map((artifact) => artifact.path).filter(Boolean)

  const lines: string[] = []
  lines.push('# Backtest sidecar manipulation (CLI)')
  lines.push('# Assumes you have the repo installed: `pip install -e .`')
  lines.push('')
  lines.push('# 1) Join candidates + features + labels into one training parquet')
  lines.push(`kalyxctl build-risk-dataset --input "${jsonPath}" --output /tmp/risk_dataset.parquet --config configs/risk_v1.yaml`)
  lines.push('')
  lines.push('# 2) Inspect the produced dataset quickly')
  lines.push('python -c \'import pandas as pd; df=pd.read_parquet("/tmp/risk_dataset.parquet"); print(df.shape); print(df.columns[:25])\'')
  lines.push('')
  if (sidecarPaths.length > 0) {
    lines.push('# 3) List sidecar parquet files on disk')
    lines.push('ls -lh \\')
    for (let idx = 0; idx < sidecarPaths.length; idx += 1) {
      const suffix = idx === sidecarPaths.length - 1 ? '' : ' \\'
      lines.push(`  "${sidecarPaths[idx]}"${suffix}`)
    }
    lines.push('')
  }
  lines.push('# 4) Build HTML report from the backtest JSON (optional)')
  lines.push(`kalyxctl report-html --input "${jsonPath}" --output /tmp/backtest-report.html --title "Backtest Report"`)
  return lines.join('\n')
}

export interface BacktestCliCommandsSectionProps {
  outputPath: string | null
  artifacts: BacktestArtifactEntry[]
}

export function BacktestCliCommandsSection({ outputPath, artifacts }: BacktestCliCommandsSectionProps) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)

  const commands = useMemo(() => buildCommands(outputPath, artifacts), [artifacts, outputPath])
  const hasRealPaths = Boolean(outputPath) || artifacts.some((artifact) => artifact.role === 'sidecar')

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(commands)
      setCopied(true)
      setCopyError(null)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyError('Unable to copy commands to clipboard')
    }
  }

  return (
    <CollapsibleSection
      title="CLI commands"
      subtitle="Join sidecars into a training dataset and inspect artifacts"
      actions={
        <Tooltip title={copied ? 'Copied' : 'Copy commands'}>
          <span>
            <Button size="small" variant="outlined" startIcon={<ContentCopyIcon />} onClick={() => void handleCopy()}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </span>
        </Tooltip>
      }
    >
      <Stack spacing={1.5}>
        {!hasRealPaths && (
          <Alert icon={<InfoOutlinedIcon />} severity="info">
            This backtest does not expose on-disk paths in the UI. Replace placeholder paths with your local report JSON and
            sidecar locations.
          </Alert>
        )}
        {copyError && <Alert severity="error">{copyError}</Alert>}
        <Typography variant="body2" color="text.secondary">
          Uses the joined dataset builder (`kalyxctl build-risk-dataset`) to combine candidate rows with `*.features.parquet`
          and `*.labels.parquet` into one parquet for modeling.
        </Typography>
        <Box
          component="pre"
          sx={{
            m: 0,
            p: 2,
            overflow: 'auto',
            borderRadius: 1,
            border: 1,
            borderColor: 'divider',
            bgcolor: 'action.hover',
            fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace',
            fontSize: '0.82rem',
            lineHeight: 1.55,
            whiteSpace: 'pre',
          }}
        >
          {commands}
        </Box>
      </Stack>
    </CollapsibleSection>
  )
}

