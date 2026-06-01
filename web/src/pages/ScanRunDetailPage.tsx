import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { fetchScanResults, fetchScanRun } from '../api/scans'
import type { ScanStatusResponse, ScanType } from '../types/scans'

type CandidateSummary = {
  symbol: string
  score?: number
  reason?: string
  details?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function extractCandidates(results: unknown): CandidateSummary[] {
  if (!isRecord(results)) return []

  const raw =
    (Array.isArray(results.candidates) && results.candidates) ||
    (Array.isArray(results.items) && results.items) ||
    (Array.isArray(results.symbols) && results.symbols) ||
    null

  if (!raw) return []

  if (raw.every((v) => typeof v === 'string')) {
    return (raw as string[]).map((symbol) => ({ symbol }))
  }

  const out: CandidateSummary[] = []
  for (const item of raw as unknown[]) {
    if (typeof item === 'string') {
      out.push({ symbol: item })
      continue
    }
    if (!isRecord(item)) continue
    const symbol = typeof item.symbol === 'string' ? item.symbol : typeof item.ticker === 'string' ? item.ticker : null
    if (!symbol) continue
    const score = typeof item.score === 'number' ? item.score : typeof item.rank === 'number' ? item.rank : undefined
    const reason =
      typeof item.reason === 'string'
        ? item.reason
        : typeof item.rationale === 'string'
          ? item.rationale
          : typeof item.why === 'string'
            ? item.why
            : undefined
    out.push({ symbol, score, reason, details: item })
  }
  return out
}

export function ScanRunDetailPage() {
  const params = useParams()
  const scanType = params.scanType as ScanType | undefined
  const scanId = params.scanId
  const [item, setItem] = useState<ScanStatusResponse | null>(null)
  const [results, setResults] = useState<unknown | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingResults, setLoadingResults] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resultsError, setResultsError] = useState<string | null>(null)

  const isValidType = useMemo(
    () => scanType === 'momentum' || scanType === 'options' || scanType === 'trend',
    [scanType],
  )

  const load = useCallback(async () => {
    if (!scanType || !scanId || !isValidType) return
    setError(null)
    setResultsError(null)
    try {
      const status = await fetchScanRun(scanType, scanId)
      setItem(status)
      setResults(null)
      if (status.results_json_path && status.status === 'completed') {
        setLoadingResults(true)
        try {
          setResults(await fetchScanResults(scanType, scanId))
        } catch (err) {
          setResultsError(err instanceof Error ? err.message : 'Failed to load results')
        } finally {
          setLoadingResults(false)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scan')
    } finally {
      setLoading(false)
    }
  }, [scanType, scanId, isValidType])

  useEffect(() => {
    setLoading(true)
    void load()
  }, [load])

  if (!scanType || !scanId || !isValidType) {
    return <Alert severity="error">Invalid scan route.</Alert>
  }

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Stack spacing={0.25}>
          <Typography variant="h4">Scan run</Typography>
          <Typography color="text.secondary" sx={{ fontFamily: 'monospace' }}>
            {scanId}
          </Typography>
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to={`/scanners/${scanType}`} startIcon={<ArrowBackIcon />}>
            Back
          </Button>
          <Button onClick={() => void load()} startIcon={<RefreshIcon />} disabled={loading}>
            Refresh
          </Button>
          <Button component="a" href={`/api/scanners/${scanType}/runs/${scanId}/results`} startIcon={<DownloadIcon />}>
            JSON
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}
      {loading ? (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <CircularProgress size={18} />
          <Typography color="text.secondary">Loading…</Typography>
        </Stack>
      ) : item ? (
        <Stack spacing={2}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.5}>
                <Stack spacing={0.25}>
                  <Typography variant="h6">Status</Typography>
                  <Typography color="text.secondary">{item.status}</Typography>
                </Stack>
                <Divider />
                <Stack spacing={0.25}>
                  <Typography variant="h6">Created</Typography>
                  <Typography color="text.secondary">{new Date(item.created_at).toLocaleString()}</Typography>
                </Stack>
                <Stack spacing={0.25}>
                  <Typography variant="h6">Argo workflow</Typography>
                  <Typography color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                    {item.argo_namespace ?? '—'} / {item.argo_workflow_name ?? '—'}
                  </Typography>
                </Stack>
                <Divider />
                <Stack spacing={0.25}>
                  <Typography variant="h6">Params</Typography>
                  <Typography
                    component="pre"
                    sx={{ m: 0, p: 1.5, borderRadius: 1, bgcolor: 'action.hover', overflow: 'auto' }}
                  >
                    {JSON.stringify(item.params ?? {}, null, 2)}
                  </Typography>
                </Stack>
                {(item.error_exception || item.error_traceback) && (
                  <>
                    <Divider />
                    <Alert severity="error">
                      <Typography sx={{ fontFamily: 'monospace' }}>{item.error_exception ?? 'Scan failed'}</Typography>
                    </Alert>
                  </>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.5}>
                <Typography variant="h6">Results</Typography>
                {item.status !== 'completed' ? (
                  <Typography color="text.secondary">Results show up after the run completes.</Typography>
                ) : loadingResults ? (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <CircularProgress size={18} />
                    <Typography color="text.secondary">Loading results…</Typography>
                  </Stack>
                ) : resultsError ? (
                  <Alert severity="warning">{resultsError}</Alert>
                ) : results ? (
                  (() => {
                    const candidates = extractCandidates(results)
                    if (candidates.length === 0) {
                      return (
                        <Typography
                          component="pre"
                          sx={{ m: 0, p: 1.5, borderRadius: 1, bgcolor: 'action.hover', overflow: 'auto' }}
                        >
                          {JSON.stringify(results, null, 2)}
                        </Typography>
                      )
                    }
                    return (
                      <Stack spacing={1}>
                        {candidates.slice(0, 200).map((c) => (
                          <Card key={c.symbol} variant="outlined">
                            <CardContent>
                              <Stack spacing={0.5}>
                                <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
                                  <Typography sx={{ fontFamily: 'monospace' }}>{c.symbol}</Typography>
                                  {typeof c.score === 'number' && (
                                    <Typography color="text.secondary">score: {c.score.toFixed(4)}</Typography>
                                  )}
                                </Stack>
                                {c.reason && <Typography color="text.secondary">{c.reason}</Typography>}
                                {!c.reason && c.details != null && (
                                  <Typography
                                    component="pre"
                                    sx={{ m: 0, p: 1.25, borderRadius: 1, bgcolor: 'action.hover', overflow: 'auto' }}
                                  >
                                    {JSON.stringify(c.details, null, 2)}
                                  </Typography>
                                )}
                              </Stack>
                            </CardContent>
                          </Card>
                        ))}
                      </Stack>
                    )
                  })()
                ) : (
                  <Typography color="text.secondary">No results yet.</Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      ) : null}

      <Typography color="text.secondary">
        View all scanners: <RouterLink to="/scanners">Scanners</RouterLink>
      </Typography>
    </Stack>
  )
}
