import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import InsightsIcon from '@mui/icons-material/Insights'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import {
  fetchDataDownloadDetail,
  fetchDataDownloadStatus,
} from '../api/dataDownloads'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { DataDownloadProgressPanel } from '../components/DataDownloadProgressPanel'
import { DataDownloadStatusChip } from '../components/DataDownloadStatusChip'
import { DownloadRecordsTable } from '../components/DownloadRecordsTable'
import { useSettings } from '../settings/useSettings'
import type {
  DataDownloadDetailResponse,
  DataDownloadStatusResponse,
} from '../types/dataDownloads'
import { formatInTimezone } from '../utils/datetime'

function buildBacktestWizardUrl(detail: DataDownloadDetailResponse): string | null {
  const successful = detail.records.filter((record) => !record.error)
  if (successful.length === 0) {
    return null
  }

  const symbols = [...new Set(successful.map((record) => record.symbol))]
  const first = successful[0]
  const params = new URLSearchParams({
    symbols: symbols.join(','),
    start_date: first.start_date,
    end_date: first.stop_date,
    resolution: first.resolution,
    feed: first.feed,
  })
  return `/backtests/new?${params.toString()}`
}

export function DataDownloadDetailPage() {
  const { platformSettings, appearance } = useSettings()
  const { jobId = '' } = useParams()
  const [detail, setDetail] = useState<DataDownloadDetailResponse | null>(null)
  const [metadata, setMetadata] = useState<DataDownloadStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const refreshIntervalMs =
    platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000
  const isActive = metadata?.status === 'pending' || metadata?.status === 'running'

  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchDataDownloadDetail(jobId)
        if (!cancelled) {
          setDetail(response)
          setMetadata((current) => current ?? response.metadata)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load download detail')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) {
      return undefined
    }

    let cancelled = false
    let timer: ReturnType<typeof window.setInterval> | undefined

    const pollStatus = async (): Promise<boolean> => {
      try {
        const status = await fetchDataDownloadStatus(jobId)
        if (cancelled) {
          return true
        }

        setMetadata(status)

        if (status.status === 'completed' || status.status === 'failed') {
          const nextDetail = await fetchDataDownloadDetail(jobId)
          if (!cancelled) {
            setDetail(nextDetail)
            setMetadata(nextDetail.metadata)
            setLoading(false)
          }
          return true
        }

        return false
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to refresh download status')
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
  }, [jobId, refreshIntervalMs])

  const backtestWizardUrl = useMemo(
    () => (detail ? buildBacktestWizardUrl(detail) : null),
    [detail],
  )

  if (loading && !metadata) {
    return (
      <Stack sx={{ py: 8, alignItems: 'center' }} spacing={1}>
        <CircularProgress />
        <Typography color="text.secondary">Loading download job…</Typography>
      </Stack>
    )
  }

  if (!metadata) {
    return (
      <Stack spacing={2}>
        <Alert severity="error">{error ?? 'Download job not found.'}</Alert>
        <Button component={RouterLink} to="/data/downloads" startIcon={<ArrowBackIcon />}>
          Back to downloads
        </Button>
      </Stack>
    )
  }

  const records = detail?.records ?? []
  const partialFailure =
    metadata.status === 'completed' &&
    metadata.failed_records > 0 &&
    metadata.successful_records > 0

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1}
        sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
      >
        <Stack spacing={1}>
          <Button
            component={RouterLink}
            to="/data/downloads"
            startIcon={<ArrowBackIcon />}
            sx={{ alignSelf: 'flex-start' }}
          >
            All downloads
          </Button>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="h4">Download job</Typography>
            <DataDownloadStatusChip status={metadata.status} />
          </Stack>
          <Typography color="text.secondary" sx={{ fontFamily: 'monospace' }}>
            {metadata.job_id}
          </Typography>
        </Stack>

        {backtestWizardUrl && (
          <Button
            component={RouterLink}
            to={backtestWizardUrl}
            variant="outlined"
            startIcon={<InsightsIcon />}
          >
            Run backtest with this universe
          </Button>
        )}
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {metadata.error_message && (
        <Alert severity="error">{metadata.error_message}</Alert>
      )}

      {partialFailure && (
        <Alert severity="warning">
          {metadata.successful_records} of {metadata.total_records} records succeeded. Failed
          symbols are listed below.
        </Alert>
      )}

      {metadata.status === 'completed' && metadata.failed_records === 0 && (
        <Alert severity="success">
          All {metadata.total_records} records downloaded successfully.
        </Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">Job summary</Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Chip
              label={`${metadata.completed_records}/${metadata.total_records} records`}
              size="small"
            />
            <Chip label={`${metadata.successful_records} succeeded`} size="small" color="success" />
            {metadata.failed_records > 0 && (
              <Chip label={`${metadata.failed_records} failed`} size="small" color="error" />
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Created{' '}
            {formatInTimezone(
              metadata.created_at,
              platformSettings.platform_behavior.timezone,
              appearance.time_display_format,
              true,
            )}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Updated{' '}
            {formatInTimezone(
              metadata.updated_at,
              platformSettings.platform_behavior.timezone,
              appearance.time_display_format,
              true,
            )}
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
            Cache folder: {metadata.output_folder}
          </Typography>
        </Stack>
      </Paper>

      {isActive && metadata && (
        <DataDownloadProgressPanel
          completedRecords={metadata.completed_records}
          totalRecords={metadata.total_records}
          successfulRecords={metadata.successful_records}
          failedRecords={metadata.failed_records}
        />
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Records</Typography>
          <DownloadRecordsTable records={records} />
        </Stack>
      </Paper>

      {records.some((record) => record.parquet_path) && (
        <CollapsibleSection title="File paths" subtitle="Parquet cache locations on the server">
          <Box sx={{ overflowX: 'auto' }}>
            <DownloadRecordsTable records={records} showPaths />
          </Box>
        </CollapsibleSection>
      )}
    </Stack>
  )
}
