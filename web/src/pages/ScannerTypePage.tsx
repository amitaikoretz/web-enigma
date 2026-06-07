import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Link,
  Stack,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { createScanRun, fetchScanParams, fetchScanRuns } from '../api/scans'
import { ScanParamsForm } from '../components/ScanParamsForm'
import type { ScanStatusResponse, ScanType } from '../types/scans'

type ScanLaunchResultState =
  | {
      status: 'success'
      message: string
      scanId: string
      scanType: ScanType
    }
  | {
      status: 'failed'
      message: string
      scanType: ScanType
    }

function titleForType(scanType: ScanType): string {
  if (scanType === 'momentum') return 'Stock Momentum Scanner'
  if (scanType === 'options') return 'Options Scanner'
  return 'Trend Scanner'
}

export function ScannerTypePage() {
  const params = useParams()
  const navigate = useNavigate()
  const scanType = params.scanType as ScanType | undefined
  const [items, setItems] = useState<ScanStatusResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scanParams, setScanParams] = useState<Record<string, unknown> | null>(null)
  const [paramsSchema, setParamsSchema] = useState<unknown | null>(null)
  const [loadingParams, setLoadingParams] = useState(false)
  const [creating, setCreating] = useState(false)
  const [launchResult, setLaunchResult] = useState<ScanLaunchResultState | null>(null)

  const isValidType = useMemo(
    () => scanType === 'momentum' || scanType === 'options' || scanType === 'trend',
    [scanType],
  )

  useEffect(() => {
    if (!scanType || !isValidType) {
      return undefined
    }

    const currentScanType = scanType
    let cancelled = false

    async function loadRuns() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchScanRuns(currentScanType)
        if (!cancelled) {
          setItems(response.items)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load scans')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadRuns()
    return () => {
      cancelled = true
    }
  }, [scanType, isValidType])

  useEffect(() => {
    if (!scanType || !isValidType) {
      return undefined
    }

    const currentScanType = scanType
    let cancelled = false

    async function loadParams() {
      setLoadingParams(true)
      try {
        const response = await fetchScanParams(currentScanType)
        if (!cancelled) {
          setScanParams(response.defaults ?? {})
          setParamsSchema(response.schema ?? null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load scan params')
        }
      } finally {
        if (!cancelled) {
          setLoadingParams(false)
        }
      }
    }

    void loadParams()
    return () => {
      cancelled = true
    }
  }, [scanType, isValidType])

  const refreshRuns = useCallback(async () => {
    if (!scanType || !isValidType) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchScanRuns(scanType)
      setItems(response.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scans')
    } finally {
      setLoading(false)
    }
  }, [scanType, isValidType])

  const onCreate = useCallback(async () => {
    if (!scanType || !isValidType) return
    setCreating(true)
    try {
      const response = await createScanRun(scanType, { params: scanParams ?? {} })
      setLaunchResult({
        status: 'success',
        message: `${titleForType(scanType)} launch submitted successfully.`,
        scanId: response.scan_id,
        scanType: response.scan_type,
      })
      void refreshRuns()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start scan'
      setLaunchResult({
        status: 'failed',
        message,
        scanType,
      })
    } finally {
      setCreating(false)
    }
  }, [scanType, isValidType, scanParams, refreshRuns])

  if (!scanType || !isValidType) {
    return (
      <Alert severity="error">
        Unknown scanner type. Go back to <RouterLink to="/scanners">Scanners</RouterLink>.
      </Alert>
    )
  }

  return (
    <Stack spacing={2.5}>
      <Dialog
        open={launchResult !== null}
        onClose={() => setLaunchResult(null)}
        aria-labelledby="scan-launch-result-title"
        aria-describedby="scan-launch-result-description"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(6px)',
              backgroundColor: 'rgba(0, 0, 0, 0.55)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              maxWidth: 520,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="scan-launch-result-title" sx={{ pb: 1 }}>
          {launchResult?.status === 'success' ? 'Scanner launched' : 'Scanner launch failed'}
        </DialogTitle>
        <DialogContent id="scan-launch-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={launchResult?.status === 'success' ? 'success' : 'error'}>
              {launchResult?.message}
            </Alert>
            {launchResult?.status === 'success' && launchResult.scanId && (
              <Typography color="text.secondary">
                You can open the new run from{' '}
                <Link component={RouterLink} to={`/scanners/${launchResult.scanType}/runs/${launchResult.scanId}`}>
                  run {launchResult.scanId}
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={() => setLaunchResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Stack spacing={0.25}>
          <Typography variant="h4">{titleForType(scanType)}</Typography>
          <Typography color="text.secondary">Last 10 runs (stored on disk) for this scanner type.</Typography>
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/scanners" startIcon={<ArrowBackIcon />}>
            All scanners
          </Button>
          <Button onClick={() => void refreshRuns()} startIcon={<RefreshIcon />} disabled={loading}>
            Refresh
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">Run a new scan</Typography>
            {loadingParams ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <CircularProgress size={18} />
                <Typography color="text.secondary">Loading parameters…</Typography>
              </Stack>
            ) : scanParams == null ? (
              <Alert severity="warning">Params schema not available for this scan type.</Alert>
            ) : paramsSchema ? (
              <ScanParamsForm schema={paramsSchema} value={scanParams} onChange={setScanParams} disabled={creating} />
            ) : (
              <Alert severity="warning">Params schema not available for this scan type.</Alert>
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'flex-start' }}>
              <Button
                variant="contained"
                startIcon={creating ? <CircularProgress size={18} /> : <PlayArrowIcon />}
                onClick={() => void onCreate()}
                disabled={creating}
              >
                Run scan (Argo)
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Divider />

      <Stack spacing={1.5}>
        <Typography variant="h6">Recent runs</Typography>
        {loading ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <CircularProgress size={18} />
            <Typography color="text.secondary">Loading scans…</Typography>
          </Stack>
        ) : items.length === 0 ? (
          <Typography color="text.secondary">No runs yet.</Typography>
        ) : (
          <Stack spacing={1}>
            {items.map((item) => (
              <Card
                key={item.scan_id}
                variant="outlined"
                sx={{ cursor: 'pointer' }}
                onClick={() => navigate(`/scanners/${scanType}/runs/${item.scan_id}`)}
              >
                <CardContent>
                  <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
                    <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontFamily: 'monospace' }}>{item.scan_id}</Typography>
                      <Typography color="text.secondary">
                        {new Date(item.created_at).toLocaleString()} · {item.status}
                      </Typography>
                    </Stack>
                    <Button
                      component="a"
                      href={`/api/scanners/${scanType}/runs/${item.scan_id}/results`}
                      onClick={(e) => e.stopPropagation()}
                      startIcon={<DownloadIcon />}
                    >
                      JSON
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  )
}
