import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import DownloadIcon from '@mui/icons-material/Download'
import BugReportIcon from '@mui/icons-material/BugReport'
import ReplayIcon from '@mui/icons-material/Replay'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  CircularProgress,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { deleteDataset, downloadDatasetParquet, fetchDatasetDetail, fetchDatasetStatus, fetchDatasetWorkflowErrors, retryDataset } from '../api/datasets'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { BacktestProgressPanel } from '../components/BacktestProgressPanel'
import { DataDownloadStatusChip } from '../components/DataDownloadStatusChip'
import { DatasetWorkflowErrorDialog } from '../components/DatasetWorkflowErrorDialog'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import { useSettings } from '../settings/useSettings'
import type { DatasetDetailResponse, DatasetStatusResponse } from '../types/datasets'
import { buildDatasetCopySnippet } from '../utils/datasetCopy'
import { familyWizardPath } from './modelLaunchRoutes'

function ArtifactPathRow({
  label,
  value,
}: {
  label: string
  value: string | null | undefined
}) {
  const [copied, setCopied] = useState(false)
  const normalizedValue = value?.trim() ? value : '—'
  const copyValue = value?.trim() ? value.trim() : ''

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1.5}
      sx={{
        alignItems: { xs: 'flex-start', sm: 'center' },
        justifyContent: 'space-between',
        p: 1.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        bgcolor: 'background.default',
      }}
    >
      <Stack spacing={0.5} sx={{ minWidth: 0, flex: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
          {label}
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>{normalizedValue}</Typography>
      </Stack>
      {copyValue && (
        <Button
          variant="outlined"
          size="small"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(copyValue)
              setCopied(true)
              window.setTimeout(() => setCopied(false), 1200)
            } catch {
              // Clipboard access may be unavailable in some environments.
            }
          }}
        >
          {copied ? 'Copied' : 'Copy path'}
        </Button>
      )}
    </Stack>
  )
}

function ChunkLayoutSummary({
  label,
  chunkCount,
  chunkDir,
}: {
  label: string
  chunkCount: number
  chunkDir: string
}) {
  const [copied, setCopied] = useState(false)
  const fileLabel = chunkCount === 1 ? 'parquet file' : 'parquet files'

  return (
    <Stack
      spacing={1.5}
      sx={{
        p: 1.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        bgcolor: 'background.default',
      }}
    >
      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
          {label}
        </Typography>
        <Typography>
          <Typography component="span" sx={{ fontWeight: 600 }}>
            {chunkCount.toLocaleString()}
          </Typography>{' '}
          {fileLabel} in
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>{chunkDir}</Typography>
      </Stack>
      <Button
        variant="outlined"
        size="small"
        sx={{ alignSelf: { xs: 'stretch', sm: 'flex-start' } }}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(chunkDir)
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1200)
          } catch {
            // Clipboard access may be unavailable in some environments.
          }
        }}
      >
        {copied ? 'Copied' : 'Copy folder path'}
      </Button>
    </Stack>
  )
}

function CopyDatasetCodeButton({
  manifestPath,
  datasetParquetPath,
}: {
  manifestPath: string | null | undefined
  datasetParquetPath: string | null | undefined
}) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const snippet = buildDatasetCopySnippet({ manifestPath, datasetParquetPath })

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
      setCopyError(null)
      window.setTimeout(() => setCopied(false), 1200)
    } catch {
      setCopyError('Unable to copy Python snippet to clipboard')
    }
  }

  return (
    <Stack spacing={1}>
      <Tooltip title={copied ? 'Copied' : 'Copy Python snippet'}>
        <span>
          <Button
            size="small"
            variant="outlined"
            startIcon={<ContentCopyIcon />}
            onClick={() => void handleCopy()}
          >
            {copied ? 'Copied' : 'Copy code'}
          </Button>
        </span>
      </Tooltip>
      {copyError && <Alert severity="error">{copyError}</Alert>}
    </Stack>
  )
}

export function DatasetDetailPage() {
  const { platformSettings } = useSettings()
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null)
  const [status, setStatus] = useState<DatasetStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [retryResult, setRetryResult] = useState<
    | { status: 'success'; message: string; datasetId: string; detailUrl: string }
    | { status: 'failed'; message: string }
    | null
  >(null)
  const [workflowErrorsOpen, setWorkflowErrorsOpen] = useState(false)
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)
  const [trainMenuAnchorEl, setTrainMenuAnchorEl] = useState<HTMLElement | null>(null)
  const refreshIntervalMs = platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchDatasetDetail(datasetId)
      .then((response) => {
        if (!cancelled) setDetail(response)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load dataset')
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  useEffect(() => {
    if (!datasetId) {
      return undefined
    }

    let cancelled = false
    let timer: ReturnType<typeof window.setInterval> | undefined

    const pollStatus = async (): Promise<boolean> => {
      try {
        const nextStatus = await fetchDatasetStatus(datasetId)
        if (cancelled) {
          return true
        }

        setStatus(nextStatus)

        if (nextStatus.status === 'completed' || nextStatus.status === 'failed') {
          const nextDetail = await fetchDatasetDetail(datasetId)
          if (!cancelled) {
            setDetail(nextDetail)
            setStatus((current) => current ?? {
              ...nextDetail.metadata,
              is_terminal: nextDetail.metadata.status === 'completed' || nextDetail.metadata.status === 'failed',
            })
            setLoading(false)
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh dataset status')
        }
        return true
      }
    }

    void (async () => {
      const terminal = await pollStatus()
      if (terminal || cancelled) {
        return
      }

      timer = window.setInterval(() => {
        void pollStatus().then((done) => {
          if (done && timer !== undefined) {
            window.clearInterval(timer)
            timer = undefined
          }
        })
      }, refreshIntervalMs)
    })()

    return () => {
      cancelled = true
      if (timer !== undefined) {
        window.clearInterval(timer)
      }
    }
  }, [datasetId, refreshIntervalMs])

  const metadata = detail?.metadata ? { ...detail.metadata, ...(status ?? {}) } : status
  const canRetry = metadata?.status === 'failed'
  const symbols = metadata?.symbols ?? (metadata?.symbol ? [metadata.symbol] : [])

  async function confirmDelete() {
    if (!metadata) {
      return
    }
    setDeleting(true)
    setError(null)
    try {
      await deleteDataset(metadata.id)
      navigate('/backtests/datasets')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete dataset')
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  async function handleDownload() {
    if (!metadata) {
      return
    }
    setDownloading(true)
    setError(null)
    try {
      await downloadDatasetParquet(metadata.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download dataset parquet')
    } finally {
      setDownloading(false)
    }
  }

  async function handleRetry() {
    if (!metadata) {
      return
    }
    setRetrying(true)
    setError(null)
    try {
      const response = await retryDataset(metadata.id)
      setRetryResult({
        status: 'success',
        message: 'Dataset retry submitted successfully.',
        datasetId: response.dataset_id,
        detailUrl: `/backtests${response.detail_url}`,
      })
      setRetryDialogOpen(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to retry dataset'
      setRetryResult({
        status: 'failed',
        message,
      })
      setRetryDialogOpen(false)
    } finally {
      setRetrying(false)
    }
  }

  function handleEditAndResubmit() {
    if (!metadata) {
      return
    }

    navigate(`/backtests/datasets/new?from=${encodeURIComponent(metadata.id)}`)
  }

  function launchModel(family: 'risk' | 'return_forecast' | 'daily_index_forecast') {
    if (!metadata) return

    setTrainMenuAnchorEl(null)
    navigate(familyWizardPath(family), {
      state: {
        sourceKind: 'dataset',
        sourceIds: [metadata.id],
        selectedCount: 1,
        selectionLabel: 'datasets',
        dailyIndexDatasetSource:
          family === 'daily_index_forecast'
            ? {
                symbol: metadata.symbol,
                start_date: metadata.start_date,
                end_date: metadata.end_date,
              }
            : null,
      },
    })
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Button component={RouterLink} to="/backtests/datasets" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to datasets
        </Button>
        <Button
          color="error"
          variant="outlined"
          startIcon={<DeleteOutlineIcon />}
          onClick={() => setDeleteOpen(true)}
          disabled={!metadata}
        >
          Delete dataset
        </Button>
      </Stack>
      {loading && !metadata ? (
        <Stack sx={{ py: 10, alignItems: 'center' }} spacing={1}>
          <CircularProgress />
          <Typography color="text.secondary">Loading dataset detail…</Typography>
        </Stack>
      ) : null}
      {error && <Alert severity="error">{error}</Alert>}
      {metadata && (
        <BacktestProgressPanel
          title="Dataset progress"
          progressPct={metadata.progress_pct ?? (metadata.status === 'completed' || metadata.status === 'failed' ? 100 : 0)}
          isIndeterminate={false}
          startedAt={metadata.created_at}
        />
      )}
      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h4">Dataset details</Typography>
          <Stack spacing={0.75}>
            <Typography variant="overline" color="text.secondary">
              Dataset
            </Typography>
            <Typography variant="h4">{metadata?.name ?? metadata?.symbol ?? datasetId}</Typography>
            <Typography color="text.secondary">
              {metadata
                ? `${metadata.provider} · ${metadata.resolution} · ${metadata.start_date} to ${metadata.end_date}`
                : 'Loading…'}
          </Typography>
          <Typography color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              ID: {metadata?.id ?? datasetId}
            </Typography>
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <Button
              variant="outlined"
              onClick={(event) => setTrainMenuAnchorEl(event.currentTarget)}
              disabled={!metadata}
              aria-haspopup="menu"
              aria-expanded={Boolean(trainMenuAnchorEl)}
            >
              Train model
            </Button>
            {canRetry && (
              <Button
                variant="contained"
                startIcon={<ReplayIcon />}
                onClick={() => setRetryDialogOpen(true)}
                disabled={!metadata || retrying}
              >
                {retrying ? 'Retrying…' : 'Retry dataset'}
              </Button>
            )}
            <Button
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={handleEditAndResubmit}
              disabled={!metadata}
            >
              Edit and resubmit
            </Button>
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              onClick={() => {
                void handleDownload()
              }}
              disabled={!metadata || downloading || metadata.status === 'pending' || metadata.status === 'running'}
              >
                {downloading ? 'Preparing download…' : 'Download parquet'}
              </Button>
            <Button
              variant="outlined"
              startIcon={<BugReportIcon />}
              onClick={() => setWorkflowErrorsOpen(true)}
              disabled={!metadata?.argo_workflow_name}
            >
              View workflow errors
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography color="text.secondary">Status</Typography>
            {metadata ? <DataDownloadStatusChip status={metadata.status} /> : <Typography>Loading…</Typography>}
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography color="text.secondary">Resolution</Typography>
            <Typography sx={{ fontFamily: 'monospace' }}>{metadata?.resolution ?? 'Loading…'}</Typography>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <Typography color="text.secondary">Symbols</Typography>
            <Typography sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>
              {symbols.length > 0 ? symbols.join(', ') : 'Loading…'}
            </Typography>
          </Stack>
          <Stack spacing={1.5}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' } }}>
              <Stack spacing={0.5}>
                <Typography variant="h6">Artifact outputs</Typography>
                <Typography color="text.secondary">
                  The combined parquet is the canonical download target. Chunk files are the sharded
                  outputs listed in the manifest and are what downstream readers should iterate over.
                </Typography>
              </Stack>
              <CopyDatasetCodeButton
                manifestPath={metadata?.manifest_path}
                datasetParquetPath={metadata?.dataset_parquet_path}
              />
            </Stack>
            <ArtifactPathRow label="Combined parquet" value={metadata?.dataset_parquet_path} />
            <ArtifactPathRow label="Manifest JSON" value={metadata?.manifest_path} />
            {detail?.market_chunks ? (
              <ChunkLayoutSummary
                label="Market chunks"
                chunkCount={detail.market_chunks.chunk_count}
                chunkDir={detail.market_chunks.chunk_dir}
              />
            ) : null}
            {metadata?.options_parquet_path || metadata?.options_manifest_path ? (
              <>
                <ArtifactPathRow label="Options parquet" value={metadata?.options_parquet_path} />
                <ArtifactPathRow label="Options manifest JSON" value={metadata?.options_manifest_path} />
                {detail?.options_chunks ? (
                  <ChunkLayoutSummary
                    label="Options chunks"
                    chunkCount={detail.options_chunks.chunk_count}
                    chunkDir={detail.options_chunks.chunk_dir}
                  />
                ) : null}
              </>
            ) : null}
            {!metadata?.dataset_parquet_path && !metadata?.manifest_path && (
              <Alert severity="info">
                The workflow has not reported final artifact paths yet. Refresh once the run completes
                or open the workflow steps dialog to inspect the combine step outputs.
              </Alert>
            )}
          </Stack>
          {metadata?.argo_workflow_name && (
            <Alert
              severity="info"
              action={
                <Stack direction="row" spacing={1}>
                  <Button size="small" variant="outlined" onClick={() => setWorkflowStepsOpen(true)}>
                    View workflow steps
                  </Button>
                  <Button size="small" variant="outlined" onClick={() => setWorkflowErrorsOpen(true)}>
                    View workflow errors
                  </Button>
                </Stack>
              }
            >
              Argo workflow: {metadata.argo_workflow_name}
              {metadata.argo_namespace ? ` (${metadata.argo_namespace})` : ''}
            </Alert>
          )}
          <Menu
            anchorEl={trainMenuAnchorEl}
            open={trainMenuAnchorEl !== null}
            onClose={() => setTrainMenuAnchorEl(null)}
          >
            <MenuItem onClick={() => launchModel('risk')}>Risk model</MenuItem>
            <MenuItem onClick={() => launchModel('return_forecast')}>Return forecast model</MenuItem>
            <MenuItem onClick={() => launchModel('daily_index_forecast')}>Daily index forecast model</MenuItem>
          </Menu>
        </Stack>
      </Paper>

      <ConfirmDialog
        open={retryDialogOpen}
        title="Retry dataset?"
        intent="info"
        icon={<ReplayIcon sx={{ fontSize: 24 }} />}
        description={
          <Typography color="text.secondary">
            This will start a new dataset run using the original launch request, including options and
            all source parameters.
          </Typography>
        }
        confirmLabel="Retry dataset"
        cancelLabel="Cancel"
        loading={retrying}
        onCancel={() => {
          if (!retrying) {
            setRetryDialogOpen(false)
          }
        }}
        onConfirm={() => {
          void handleRetry()
        }}
      />
      <Dialog
        open={retryResult !== null}
        onClose={() => setRetryResult(null)}
        aria-labelledby="dataset-retry-result-title"
        aria-describedby="dataset-retry-result-description"
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
        <DialogTitle id="dataset-retry-result-title" sx={{ pb: 1 }}>
          {retryResult?.status === 'success' ? 'Dataset retry submitted' : 'Dataset retry failed'}
        </DialogTitle>
        <DialogContent id="dataset-retry-result-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Alert severity={retryResult?.status === 'success' ? 'success' : 'error'}>
              {retryResult?.message}
            </Alert>
            {retryResult?.status === 'success' && retryResult.datasetId && (
              <Typography color="text.secondary">
                You can open the new dataset from{' '}
                <Button
                  component={RouterLink}
                  to={retryResult.detailUrl}
                  sx={{ px: 0.5, minWidth: 'auto', fontWeight: 600, textTransform: 'none' }}
                >
                  {retryResult.datasetId}
                </Button>
                .
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, justifyContent: 'flex-start' }}>
          <Button onClick={() => setRetryResult(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={deleteOpen}
        title="Delete dataset?"
        description={
          <Stack spacing={1.5}>
            <Typography color="text.secondary">
              This permanently removes the dataset record and its parquet artifacts. This action cannot be undone.
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              {metadata?.id ?? datasetId}
            </Typography>
          </Stack>
        }
        confirmLabel="Delete dataset"
        cancelLabel="Keep dataset"
        loading={deleting}
        onCancel={() => {
          if (!deleting) {
            setDeleteOpen(false)
          }
        }}
        onConfirm={() => {
          void confirmDelete()
        }}
      />
      <DatasetWorkflowErrorDialog
        datasetId={metadata?.id ?? null}
        open={workflowErrorsOpen}
        onClose={() => setWorkflowErrorsOpen(false)}
        fetchWorkflowErrors={fetchDatasetWorkflowErrors}
      />
      <WorkflowStepsDialog
        open={workflowStepsOpen}
        onClose={() => setWorkflowStepsOpen(false)}
        entityKind="Dataset"
        entityLabel={metadata?.name ?? metadata?.id ?? datasetId}
        workflowName={metadata?.argo_workflow_name ?? ''}
        namespace={metadata?.argo_namespace ?? null}
        workflowTitle={metadata?.name ?? metadata?.id ?? null}
      />
    </Stack>
  )
}
