import { Box, Chip, keyframes } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'

import { useSettings } from '../settings/useSettings'

export type StatusColor = 'success' | 'error' | 'info' | 'warning'

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
`

export function titleCaseStatus(value: string): string {
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function StatusPill({
  label,
  color,
  pulseDot = false,
}: {
  label: string
  color: StatusColor
  pulseDot?: boolean
}) {
  const theme = useTheme()
  const { appearance } = useSettings()
  const main = theme.palette[color].main

  return (
    <Chip
      label={
        <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
          <Box
            component="span"
            sx={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              bgcolor: main,
              flexShrink: 0,
              animation:
                pulseDot && !appearance.reduced_motion
                  ? `${pulse} 1.6s ease-in-out infinite`
                  : undefined,
            }}
          />
          {label}
        </Box>
      }
      size="small"
      sx={{
        height: 22,
        fontWeight: 500,
        letterSpacing: 0,
        textTransform: 'none',
        color: main,
        bgcolor: alpha(main, 0.12),
        border: `1px solid ${alpha(main, 0.24)}`,
        '& .MuiChip-label': {
          px: 1,
        },
      }}
    />
  )
}
