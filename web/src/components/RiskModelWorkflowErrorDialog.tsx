import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'

import { fetchRiskModelWorkflowErrors } from '../api/riskModels'
import type { RiskModelWorkflowErrorResponse } from '../types/riskModels'

interface RiskModelWorkflowErrorDialogProps {
  groupId: string | null
  open: boolean
  onClose: () => void
}

function ErrorField({
  label,
  value,
}: {
  label: string
  value: string | null | undefined
}) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
        {label}
      </Typography>
      <Box
        sx={{
          fontFamily: 'monospace',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.default',
          px: 1.5,
          py: 1,
          minHeight: 44,
        }}
      >
        {value?.trim() ? value : '—'}
      </Box>
    </Stack>
  )
}

export function RiskModelWorkflowErrorDialog({
  groupId,
  open,
  onClose,
}: RiskModelWorkflowErrorDialogProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState<RiskModelWorkflowErrorResponse | null>(null)

  useEffect(() => {
    if (!open || !groupId) {
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setDetails(null)

    void fetchRiskModelWorkflowErrors(groupId)
      .then((response) => {
        if (!cancelled) {
          setDetails(response)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workflow errors')
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
  }, [groupId, open])

  return (
    <Dialog
      open={open && groupId !== null}
      onClose={loading ? undefined : onClose}
      aria-labelledby="risk-model-workflow-error-title"
      fullWidth
      maxWidth="md"
      slotProps={{
        backdrop: {
          sx: {
            backdropFilter: 'blur(4px)',
            backgroundColor: 'rgba(0, 0, 0, 0.45)',
          },
        },
        paper: {
          sx: {
            width: '100%',
          },
        },
      }}
    >
      <DialogTitle id="risk-model-workflow-error-title" sx={{ pb: 1 }}>
        <Stack spacing={1}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="h6" component="span">
              Workflow errors
            </Typography>
            {details?.argo_phase ? <Chip size="small" label={details.argo_phase} /> : null}
            {details?.available === false ? <Chip size="small" color="warning" label="Unavailable" /> : null}
          </Stack>
          <Typography color="text.secondary" variant="body2">
            {groupId ? `Risk model ${groupId}` : 'Risk model'}
          </Typography>
        </Stack>
      </DialogTitle>

      <DialogContent dividers sx={{ pt: 2 }}>
        {loading ? (
          <Stack sx={{ py: 4, alignItems: 'center' }} spacing={1.5}>
            <CircularProgress />
            <Typography color="text.secondary">Loading workflow errors…</Typography>
          </Stack>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : details ? (
          <Stack spacing={2}>
            {details.status_message && (
              <Alert severity={details.available ? 'info' : 'warning'}>{details.status_message}</Alert>
            )}
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip size="small" variant="outlined" label={`Namespace: ${details.argo_namespace ?? '—'}`} />
              <Chip size="small" variant="outlined" label={`Workflow: ${details.argo_workflow_name ?? '—'}`} />
              <Chip size="small" variant="outlined" label={`Phase: ${details.argo_phase ?? '—'}`} />
              <Chip size="small" variant="outlined" label={`Node: ${details.failed_node_name ?? '—'}`} />
              <Chip size="small" variant="outlined" label={`Template: ${details.failed_template_name ?? '—'}`} />
            </Stack>

            <Divider />

            <Stack spacing={2}>
              <ErrorField label="error-exception" value={details.error_exception} />
              <ErrorField label="error-code-location" value={details.error_code_location} />
              <Stack spacing={0.5}>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                  error-call-stack
                </Typography>
                <Box
                  sx={{
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    bgcolor: 'background.default',
                    px: 1.5,
                    py: 1,
                    minHeight: 72,
                  }}
                >
                  {details.error_call_stack.length > 0 ? details.error_call_stack.join('\n') : '—'}
                </Box>
              </Stack>
              <Stack spacing={0.5}>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                  error-traceback
                </Typography>
                <Box
                  sx={{
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    bgcolor: 'background.default',
                    px: 1.5,
                    py: 1,
                    minHeight: 120,
                  }}
                >
                  {details.error_traceback?.trim() ? details.error_traceback : '—'}
                </Box>
              </Stack>
            </Stack>
          </Stack>
        ) : (
          <Typography color="text.secondary">No workflow error details loaded.</Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, pt: 1 }}>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  )
}
