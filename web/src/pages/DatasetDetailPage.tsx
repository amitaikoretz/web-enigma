import ArrowBackIcon from '@mui/icons-material/ArrowBack'
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
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { deleteDataset, downloadDatasetParquet, fetchDatasetDetail, fetchDatasetStatus, fetchDatasetWorkflowErrors, retryDataset } from '../api/datasets'
import { createRiskModel } from '../api/riskModels'
import { createReturnForecastModel } from '../api/returnForecastModels'
import { createDailyIndexForecastModel } from '../api/dailyIndexForecastModels'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { BacktestProgressPanel } from '../components/BacktestProgressPanel'
import { DataDownloadStatusChip } from '../components/DataDownloadStatusChip'
import { DatasetWorkflowErrorDialog } from '../components/DatasetWorkflowErrorDialog'
import { ModelTrainingLaunchDialog, type DailyIndexDatasetSource, type ModelTrainingFamily, type ModelTrainingLaunchPayload } from '../components/ModelTrainingLaunchDialog'
import { WorkflowStepsDialog } from '../components/WorkflowStepsDialog'
import type { DatasetDetailResponse, DatasetStatusResponse } from '../types/datasets'

export function DatasetDetailPage() {
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null)
  const [status, setStatus] = useState<DatasetStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [launchFamily, setLaunchFamily] = useState<ModelTrainingFamily | null>(null)
  const [launchSubmitting, setLaunchSubmitting] = useState(false)
  const [launchError, setLaunchError] = useState<string | null>(null)
  const [retryResult, setRetryResult] = useState<
    | { status: 'success'; message: string; datasetId: string; detailUrl: string }
    | { status: 'failed'; message: string }
    | null
  >(null)
  const [workflowErrorsOpen, setWorkflowErrorsOpen] = useState(false)
  const [workflowStepsOpen, setWorkflowStepsOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchDatasetDetail(datasetId)
      .then((response) => {
        if (!cancelled) setDetail(response)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load dataset')
      })
    fetchDatasetStatus(datasetId)
      .then((response) => {
        if (!cancelled) setStatus(response)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [datasetId])

  const metadata = detail?.metadata ?? status
  const isActive = metadata?.status === 'pending' || metadata?.status === 'running'
  const canRetry = metadata?.status === 'failed'

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

  async function submitModelLaunch(payload: ModelTrainingLaunchPayload) {
    if (!metadata) return
    setLaunchSubmitting(true)
    setLaunchError(null)
    setError(null)
    try {
      const response =
        payload.family === 'risk'
          ? await createRiskModel({
              ...(payload.request as any),
              dataset_ids: [metadata.id],
            })
          : payload.family === 'return_forecast'
          ? await createReturnForecastModel({
              ...(payload.request as any),
              dataset_ids: [metadata.id],
            })
          : await createDailyIndexForecastModel({
              name: (payload.request as any).name ?? null,
              universe: (payload.request as any).universe,
              feature_config: (payload.request as any).feature_config,
              walk_forward: (payload.request as any).walk_forward,
              train_config: (payload.request as any).train_config,
              costs: (payload.request as any).costs,
              data_cache: (payload.request as any).data_cache,
            })
      setLaunchFamily(null)
      setRetryResult({
        status: 'success',
        message: 'Model launch submitted successfully.',
        datasetId: (response as any).group_id,
        detailUrl: `/models/risk/${(response as any).group_id}`,
      } as any)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to launch model'
      setLaunchError(message)
      setError(message)
    } finally {
      setLaunchSubmitting(false)
    }
  }

  const dailyIndexDatasetSource: DailyIndexDatasetSource | null = metadata
    ? {
        symbol: metadata.symbol,
        start_date: metadata.start_date,
        end_date: metadata.end_date,
      }
    : null

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
      {error && <Alert severity="error">{error}</Alert>}
      {metadata && (
        <BacktestProgressPanel
          title="Dataset progress"
          progressPct={metadata.progress_pct ?? (metadata.status === 'completed' || metadata.status === 'failed' ? 100 : 0)}
          isIndeterminate={isActive}
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
            <Button variant="outlined" onClick={() => setLaunchFamily('risk')} disabled={!metadata}>
              Train risk model
            </Button>
            <Button variant="outlined" onClick={() => setLaunchFamily('return_forecast')} disabled={!metadata}>
              Train return forecast
            </Button>
            <Button variant="outlined" onClick={() => setLaunchFamily('daily_index_forecast')} disabled={!metadata}>
              Train daily index forecast
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
          <Typography sx={{ fontFamily: 'monospace' }}>Output: {metadata?.output_dir ?? '—'}</Typography>
          <Typography sx={{ fontFamily: 'monospace' }}>Parquet: {metadata?.dataset_parquet_path ?? '—'}</Typography>
          <Typography sx={{ fontFamily: 'monospace' }}>Manifest: {metadata?.manifest_path ?? '—'}</Typography>
          <Typography sx={{ fontFamily: 'monospace' }}>Options parquet: {metadata?.options_parquet_path ?? '—'}</Typography>
          <Typography sx={{ fontFamily: 'monospace' }}>Options manifest: {metadata?.options_manifest_path ?? '—'}</Typography>
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
      <ModelTrainingLaunchDialog
        open={launchFamily !== null}
        allowedFamilies={['risk', 'return_forecast', 'daily_index_forecast']}
        selectedCount={metadata ? 1 : 0}
        selectionLabel="datasets"
        submitting={launchSubmitting}
        error={launchError}
        dailyIndexDatasetSource={dailyIndexDatasetSource}
        onClose={() => setLaunchFamily(null)}
        onSubmit={submitModelLaunch}
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
