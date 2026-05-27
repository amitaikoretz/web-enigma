import { alpha, Box, keyframes, Stack, Tooltip, Typography, useTheme } from '@mui/material'
import { useMemo } from 'react'

import { useApiHealth } from '../hooks/useApiHealth'
import { useSettings } from '../settings/useSettings'
import { formatInTimezone } from '../utils/datetime'

const softPulse = keyframes`
  0%, 100% {
    transform: scale(1);
    opacity: 0.35;
  }
  50% {
    transform: scale(1.6);
    opacity: 0;
  }
`

const gentleFade = keyframes`
  0%, 100% {
    opacity: 0.45;
  }
  50% {
    opacity: 0.9;
  }
`

const DOT_SIZE = 6

export function ApiHealthIndicator() {
  const theme = useTheme()
  const { appearance, platformSettings } = useSettings()
  const { status, latencyMs, lastCheckedAt, error } = useApiHealth()
  const reducedMotion = appearance.reduced_motion
  const timezone = platformSettings.platform_behavior.timezone

  const palette = useMemo(() => {
    if (status === 'connected') {
      return {
        color: alpha(theme.palette.success.main, theme.palette.mode === 'dark' ? 0.82 : 0.72),
        label: 'Connected',
        detail: latencyMs !== null ? `${latencyMs} ms` : 'Reachable',
      }
    }
    if (status === 'checking') {
      return {
        color: alpha(theme.palette.text.secondary, 0.55),
        label: 'Checking',
        detail: 'Verifying connection…',
      }
    }
    return {
      color: alpha(theme.palette.error.main, 0.78),
      label: 'Offline',
      detail: error ?? 'Unreachable',
    }
  }, [
    error,
    latencyMs,
    status,
    theme.palette.error.main,
    theme.palette.mode,
    theme.palette.success.main,
    theme.palette.text.secondary,
  ])

  const lastCheckedLabel = lastCheckedAt
    ? formatInTimezone(lastCheckedAt, timezone, appearance.time_display_format, true)
    : null

  const tooltip = (
    <Stack spacing={0.25}>
      <Typography variant="caption" sx={{ fontWeight: 600, letterSpacing: '0.02em' }}>
        API {palette.label.toLowerCase()}
      </Typography>
      <Typography variant="caption" color="inherit" sx={{ opacity: 0.72 }}>
        {palette.detail}
        {lastCheckedLabel ? ` · ${lastCheckedLabel}` : ''}
      </Typography>
    </Stack>
  )

  return (
    <Tooltip title={tooltip} arrow placement="bottom" enterDelay={400}>
      <Box
        component="span"
        role="status"
        aria-live="polite"
        aria-label={`API ${palette.label.toLowerCase()}`}
        sx={{
          position: 'relative',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 10,
          height: 10,
          flexShrink: 0,
          verticalAlign: 'middle',
          cursor: 'default',
          opacity: status === 'connected' ? 0.88 : 1,
          transition: 'opacity 0.3s ease',
          '&:hover': {
            opacity: 1,
          },
        }}
      >
        {status === 'connected' && !reducedMotion ? (
          <Box
            aria-hidden
            sx={{
              position: 'absolute',
              width: DOT_SIZE,
              height: DOT_SIZE,
              borderRadius: '50%',
              bgcolor: palette.color,
              animation: `${softPulse} 3.6s ease-in-out infinite`,
            }}
          />
        ) : null}
        <Box
          sx={{
            width: DOT_SIZE,
            height: DOT_SIZE,
            borderRadius: '50%',
            bgcolor: palette.color,
            animation:
              status === 'checking' && !reducedMotion
                ? `${gentleFade} 1.8s ease-in-out infinite`
                : undefined,
          }}
        />
      </Box>
    </Tooltip>
  )
}
