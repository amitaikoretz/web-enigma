import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DownloadIcon from '@mui/icons-material/Download'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Link,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useState } from 'react'

import { backtestConfigUrl } from '../api/backtests'
import { CollapsibleSection } from './CollapsibleSection'

interface BacktestConfigInspectorProps {
  backtestId: string
  inputConfigPath: string | null
  configSha256: string
  defaultExpanded?: boolean
}

export function BacktestConfigInspector({
  backtestId,
  inputConfigPath,
  configSha256,
  defaultExpanded = false,
}: BacktestConfigInspectorProps) {
  const [yamlText, setYamlText] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const configUrl = backtestConfigUrl(backtestId)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(configUrl)
      if (!response.ok) {
        throw new Error('Failed to load backtest configuration')
      }
      setYamlText(await response.text())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load backtest configuration')
    } finally {
      setLoading(false)
    }
  }, [configUrl])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  async function handleCopy() {
    if (!yamlText) {
      return
    }
    try {
      await navigator.clipboard.writeText(yamlText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Unable to copy configuration to clipboard')
    }
  }

  return (
    <CollapsibleSection title="Backtest configuration" defaultExpanded={defaultExpanded}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
        >
          <Stack spacing={0.75}>
            {inputConfigPath ? (
              <Typography variant="body2" color="text.secondary">
                Source definition:{' '}
                <Box component="code" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                  {inputConfigPath}
                </Box>
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Generated from the submitted backtest definition.
              </Typography>
            )}
            <Typography variant="body2" color="text.secondary">
              Config hash:{' '}
              <Box component="code" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                {configSha256.slice(0, 12)}
              </Box>
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button
              component="a"
              href={configUrl}
              target="_blank"
              rel="noopener noreferrer"
              size="small"
              variant="outlined"
              startIcon={<OpenInNewIcon />}
            >
              Open YAML
            </Button>
            <Button
              component="a"
              href={configUrl}
              download={`${backtestId}.yaml`}
              size="small"
              variant="outlined"
              startIcon={<DownloadIcon />}
            >
              Download
            </Button>
            <Tooltip title={copied ? 'Copied' : 'Copy YAML'}>
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<ContentCopyIcon />}
                  disabled={!yamlText || loading}
                  onClick={() => void handleCopy()}
                >
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              </span>
            </Tooltip>
          </Stack>
        </Stack>

        {inputConfigPath && (
          <Typography variant="body2" color="text.secondary">
            The saved YAML below matches the submitted definition. The original file path is shown for traceability.
          </Typography>
        )}

        {!inputConfigPath && (
          <Typography variant="body2" color="text.secondary">
            View or download the YAML at{' '}
            <Link href={configUrl} target="_blank" rel="noopener noreferrer">
              {backtestId.slice(0, 8)}.yaml
            </Link>
            .
          </Typography>
        )}

        {error && <Alert severity="error">{error}</Alert>}

        {loading ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', py: 2 }}>
            <CircularProgress size={18} />
            <Typography color="text.secondary">Loading configuration…</Typography>
          </Stack>
        ) : yamlText ? (
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              maxHeight: 420,
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
            {yamlText}
          </Box>
        ) : null}
      </Stack>
    </CollapsibleSection>
  )
}
