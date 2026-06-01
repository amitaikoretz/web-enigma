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
  Divider,
  Stack,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { createScanRun, fetchScanParams, fetchScanRuns } from '../api/scans'
import { ScanParamsForm } from '../components/ScanParamsForm'
import type { ScanStatusResponse, ScanType } from '../types/scans'

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

  const isValidType = useMemo(
    () => scanType === 'momentum' || scanType === 'options' || scanType === 'trend',
    [scanType],
  )

  const load = useCallback(async () => {
    if (!scanType || !isValidType) return
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

  useEffect(() => {
    setLoading(true)
    void load()
  }, [load])

  useEffect(() => {
    if (!scanType || !isValidType) return
    setLoadingParams(true)
    void (async () => {
      try {
        const response = await fetchScanParams(scanType)
        setScanParams(response.defaults ?? {})
        setParamsSchema(response.schema ?? null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load scan params')
      } finally {
        setLoadingParams(false)
      }
    })()
  }, [scanType, isValidType])

  const onCreate = useCallback(async () => {
    if (!scanType || !isValidType) return
    setCreating(true)
    setError(null)
    try {
      await createScanRun(scanType, { params: scanParams ?? {} })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start scan')
    } finally {
      setCreating(false)
    }
  }, [scanType, isValidType, scanParams, load])

  if (!scanType || !isValidType) {
    return (
      <Alert severity="error">
        Unknown scanner type. Go back to <RouterLink to="/scanners">Scanners</RouterLink>.
      </Alert>
    )
  }

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Stack spacing={0.25}>
          <Typography variant="h4">{titleForType(scanType)}</Typography>
          <Typography color="text.secondary">Last 10 runs (stored on disk) for this scanner type.</Typography>
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/scanners" startIcon={<ArrowBackIcon />}>
            All scanners
          </Button>
          <Button onClick={() => void load()} startIcon={<RefreshIcon />} disabled={loading}>
            Refresh
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">Run a new scan</Typography>
            {loadingParams || scanParams == null ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <CircularProgress size={18} />
                <Typography color="text.secondary">Loading parameters…</Typography>
              </Stack>
            ) : paramsSchema ? (
              <ScanParamsForm schema={paramsSchema} value={scanParams} onChange={setScanParams} disabled={creating} />
            ) : (
              <Alert severity="warning">Params schema not available for this scan type.</Alert>
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
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
