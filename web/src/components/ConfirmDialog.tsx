import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined'
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import type { ReactNode } from 'react'

export interface ConfirmDialogProps {
  open: boolean
  title: string
  description: ReactNode
  intent?: 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error'
  icon?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  intent = 'error',
  icon,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const resolvedIcon = icon ?? <WarningAmberOutlinedIcon sx={{ fontSize: 24 }} />

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onCancel}
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
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
            maxWidth: 440,
            p: 0.5,
          },
        },
      }}
    >
      <DialogTitle id="confirm-dialog-title" sx={{ pb: 1 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
          <Box
            sx={(theme) => ({
              display: 'grid',
              placeItems: 'center',
              width: 44,
              height: 44,
              borderRadius: '50%',
              bgcolor: alpha(theme.palette[intent].main, 0.14),
              color: `${intent}.main`,
              flexShrink: 0,
            })}
          >
            {resolvedIcon}
          </Box>
          <Stack spacing={0.5} sx={{ pt: 0.25, minWidth: 0 }}>
            <Typography variant="h6" component="span">
              {title}
            </Typography>
          </Stack>
        </Stack>
      </DialogTitle>

      <DialogContent id="confirm-dialog-description" sx={{ pt: 0 }}>
        {typeof description === 'string' ? (
          <Typography color="text.secondary">{description}</Typography>
        ) : (
          description
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, gap: 1 }}>
        <Button onClick={onCancel} disabled={loading} variant="outlined" color="inherit">
          {cancelLabel}
        </Button>
        <Button
          onClick={onConfirm}
          disabled={loading}
          variant="contained"
          color={intent}
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
