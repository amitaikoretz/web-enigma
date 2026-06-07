import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material'
import { useEffect, useState } from 'react'

import type { DatasetWorkflowErrorResponse } from '../types/datasets'

async function copyText(value: string): Promise<boolean> {
  if (!value.trim() || !navigator.clipboard?.writeText) return false
  await navigator.clipboard.writeText(value)
  return true
}

function CopyableField({ label, value }: { label: string; value: string | null | undefined }) {
  const [copied, setCopied] = useState(false)
  const normalizedValue = value?.trim() ? value : '—'
  const copyValue = value?.trim() ? value.trim() : ''
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>{label}</Typography>
        {copyValue && (
          <Tooltip title={copied ? 'Copied' : 'Copy'}>
            <IconButton size="small" aria-label={`Copy ${label.toLowerCase()}`} onClick={async () => { if (await copyText(copyValue)) { setCopied(true); window.setTimeout(() => setCopied(false), 1200) } }} sx={{ color: copied ? 'success.main' : 'text.secondary' }}>
              <ContentCopyIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Stack>
      <Paper variant="outlined" sx={{ px: 1.25, py: 1, bgcolor: 'background.default' }}>
        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace', lineHeight: 1.5 }}>{normalizedValue}</Typography>
      </Paper>
    </Stack>
  )
}

function CopyableCodeBlock({ label, value, minHeight }: { label: string; value: string; minHeight: number }) {
  const [copied, setCopied] = useState(false)
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>{label}</Typography>
        <Tooltip title={copied ? 'Copied' : 'Copy'}>
          <IconButton size="small" aria-label={`Copy ${label.toLowerCase()}`} onClick={async () => { if (value.trim() && await copyText(value)) { setCopied(true); window.setTimeout(() => setCopied(false), 1200) } }} sx={{ color: copied ? 'success.main' : 'text.secondary' }}>
            <ContentCopyIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
      </Stack>
      <Box component="pre" sx={{ m: 0, p: 1.25, minHeight, borderRadius: 1, border: '1px solid', borderColor: 'divider', bgcolor: 'background.default', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace', fontSize: '0.85rem', lineHeight: 1.55, overflow: 'auto' }}>{value.trim() ? value : '—'}</Box>
    </Stack>
  )
}

export function DatasetWorkflowErrorDialog({
  datasetId,
  open,
  onClose,
  fetchWorkflowErrors,
}: {
  datasetId: string | null
  open: boolean
  onClose: () => void
  fetchWorkflowErrors: (datasetId: string) => Promise<DatasetWorkflowErrorResponse>
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState<DatasetWorkflowErrorResponse | null>(null)
  useEffect(() => {
    if (!open || !datasetId) return undefined
    let cancelled = false
    setLoading(true); setError(null); setDetails(null)
    void fetchWorkflowErrors(datasetId).then((response) => { if (!cancelled) setDetails(response) }).catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load workflow errors') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [datasetId, fetchWorkflowErrors, open])
  const summaryText = details?.error_exception?.trim() && details?.error_code_location?.trim() ? `${details.error_exception.trim()} at ${details.error_code_location.trim()}` : details?.error_exception?.trim() ?? details?.error_code_location?.trim() ?? 'No error summary available'
  return (
    <Dialog open={open && datasetId !== null} onClose={loading ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ pb: 1 }}>
        <Stack spacing={1}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="h6" component="span">Workflow errors</Typography>
            {details?.argo_phase ? <Chip size="small" label={details.argo_phase} /> : null}
            {details?.available === false ? <Chip size="small" color="warning" label="Unavailable" /> : null}
          </Stack>
          <Typography color="text.secondary" variant="body2">{datasetId ? `Dataset ${datasetId}` : 'Dataset'}</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent dividers sx={{ pt: 2 }}>
        {loading ? <Stack sx={{ py: 4, alignItems: 'center' }} spacing={1.5}><CircularProgress /><Typography color="text.secondary">Loading workflow errors…</Typography></Stack> : error ? <Alert severity="error">{error}</Alert> : details ? (
          <Stack spacing={2}>
            {details.status_message && <Alert severity={details.available ? 'info' : 'warning'}>{details.status_message}</Alert>}
            <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
              <Stack spacing={1.5}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Failure summary</Typography>
                <Typography color="text.secondary" variant="body2">{summaryText}</Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                  <Chip size="small" variant="outlined" label={`Namespace: ${details.argo_namespace ?? '—'}`} />
                  <Chip size="small" variant="outlined" label={`Workflow: ${details.argo_workflow_name ?? '—'}`} />
                  <Chip size="small" variant="outlined" label={`Phase: ${details.argo_phase ?? '—'}`} />
                  <Chip size="small" variant="outlined" label={`Node: ${details.failed_node_name ?? '—'}`} />
                  <Chip size="small" variant="outlined" label={`Template: ${details.failed_template_name ?? '—'}`} />
                </Stack>
              </Stack>
            </Paper>
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <Box sx={{ flex: 1 }}><CopyableField label="error-exception" value={details.error_exception} /></Box>
                <Box sx={{ flex: 1 }}><CopyableField label="error-code-location" value={details.error_code_location} /></Box>
              </Stack>
              <CopyableCodeBlock label="error-call-stack" value={details.error_call_stack.length > 0 ? details.error_call_stack.join('\n') : '—'} minHeight={96} />
              <CopyableCodeBlock label="error-traceback" value={details.error_traceback?.trim() ? details.error_traceback : '—'} minHeight={160} />
            </Stack>
          </Stack>
        ) : <Typography color="text.secondary">No workflow error details loaded.</Typography>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5, pt: 1 }}>
        <Button onClick={onClose} variant="contained">Close</Button>
      </DialogActions>
    </Dialog>
  )
}
