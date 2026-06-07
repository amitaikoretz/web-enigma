import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'

import { fetchLatestMarketOverview, launchMarketOverview } from '../api/marketOverview'
import { useSettings } from '../settings/useSettings'
import type { MarketOverviewSnapshot } from '../types/marketOverview'

function formatPercent(value: number): string {
  return `${Math.round(value)}%`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

export function MarketOverviewPage() {
  const { platformSettings } = useSettings()
  const [snapshot, setSnapshot] = useState<MarketOverviewSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const refreshIntervalSeconds = platformSettings.platform_behavior.market_overview_refresh_interval_seconds
  const nextRefreshAt =
    snapshot && !Number.isNaN(new Date(snapshot.updated_at).getTime())
      ? new Date(new Date(snapshot.updated_at).getTime() + refreshIntervalSeconds * 1000)
      : null

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchLatestMarketOverview()
      .then((next) => {
        if (!cancelled) {
          setSnapshot(next)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load market overview')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRefresh() {
    setRefreshing(true)
    setError(null)
    try {
      await launchMarketOverview()
      const next = await fetchLatestMarketOverview()
      setSnapshot(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to launch market overview')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Market Overview</Typography>
        <Typography color="text.secondary">
          A persisted daily regime read with confidence, fragility, and recent developments.
        </Typography>
        <Box>
          <Button variant="contained" onClick={() => void handleRefresh()} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh overview'}
          </Button>
        </Box>
      </Stack>

      {loading && <Alert severity="info">Loading market overview…</Alert>}
      {error && <Alert severity="error">{error}</Alert>}
      {!loading && !error && !snapshot && <Alert severity="warning">No market overview snapshot is available yet.</Alert>}

      {snapshot && (
        <Stack spacing={3}>
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="h5">{snapshot.top_regime ?? '—'}</Typography>
                <Chip label={snapshot.status} size="small" />
                <Chip label={`Confidence ${formatPercent(snapshot.confidence)}`} size="small" variant="outlined" />
                <Chip label={`Fragility ${formatPercent(snapshot.fragility)}`} size="small" variant="outlined" />
                {Date.now() - new Date(snapshot.updated_at).getTime() > 60 * 60 * 1000 ? (
                  <Chip label="Stale" size="small" color="warning" variant="outlined" />
                ) : null}
              </Stack>
              <Typography>{snapshot.summary_text ?? 'No summary available.'}</Typography>
              <Typography color="text.secondary">
                Last refreshed {formatDateTime(snapshot.updated_at)} · Next refresh {formatDateTime(nextRefreshAt?.toISOString())}
              </Typography>
              <Typography color="text.secondary">
                As of {formatDateTime(snapshot.as_of)} · Workflow {snapshot.argo_workflow_name ?? '—'}
              </Typography>
              {snapshot.error_message && <Alert severity="error">{snapshot.error_message}</Alert>}
            </Stack>
          </Paper>

          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Pillar Scores
              </Typography>
              <Stack spacing={1}>
                {Object.entries(snapshot.pillar_scores).map(([pillar, value]) => (
                  <Typography key={pillar} variant="body2">
                    <strong>{pillar}</strong>: {typeof value === 'number' ? value.toFixed(2) : JSON.stringify(value)}
                  </Typography>
                ))}
              </Stack>
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Recent Developments
              </Typography>
              <Stack spacing={1}>
                {snapshot.developments.length === 0 ? (
                  <Typography color="text.secondary">No recent developments recorded.</Typography>
                ) : (
                  snapshot.developments.map((item, index) => (
                    <Typography key={index} variant="body2">
                      {typeof item.title === 'string' ? item.title : `Development ${index + 1}`}
                    </Typography>
                  ))
                )}
              </Stack>
            </Paper>
          </Box>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Probability Distribution
            </Typography>
            <Stack spacing={1}>
              {Object.entries(snapshot.probabilities).map(([regime, value]) => (
                <Stack key={regime} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Typography sx={{ minWidth: 280 }}>{regime}</Typography>
                  <Typography color="text.secondary">{formatPercent(value * 100)}</Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Stack>
      )}
    </Stack>
  )
}
