import { Box, Paper, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'

export type MetricTone = 'default' | 'positive' | 'negative' | 'muted'

export interface MetricItem {
  label: string
  value: string
  tone?: MetricTone
}

function toneColor(tone: MetricTone): string | undefined {
  switch (tone) {
    case 'positive':
      return 'success.main'
    case 'negative':
      return 'error.main'
    case 'muted':
      return 'text.secondary'
    default:
      return 'text.primary'
  }
}

export function DiagnosticsSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, md: 2.5 },
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {description && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {description}
          </Typography>
        )}
      </Box>
      {children}
    </Paper>
  )
}

export function MetricTile({ label, value, tone = 'default' }: MetricItem) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.75,
        height: '100%',
        bgcolor: 'background.default',
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', textTransform: 'uppercase', letterSpacing: 0.4, lineHeight: 1.4 }}
      >
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{
          mt: 0.75,
          fontWeight: 600,
          fontSize: '1.05rem',
          lineHeight: 1.3,
          color: toneColor(tone),
        }}
      >
        {value}
      </Typography>
    </Paper>
  )
}

export function MetricGrid({ items, minColumnWidth = 150 }: { items: MetricItem[]; minColumnWidth?: number }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${minColumnWidth}px, 1fr))`,
        gap: 1.5,
      }}
    >
      {items.map((item) => (
        <MetricTile key={item.label} {...item} />
      ))}
    </Box>
  )
}

export function DiagnosticsTableShell({
  title,
  children,
}: {
  title?: string
  children: ReactNode
}) {
  return (
    <Stack spacing={1}>
      {title && (
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
      )}
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        {children}
      </Paper>
    </Stack>
  )
}

export function pnlTone(value: number | null | undefined): MetricTone {
  if (value === null || value === undefined) {
    return 'muted'
  }
  if (value > 0) {
    return 'positive'
  }
  if (value < 0) {
    return 'negative'
  }
  return 'default'
}

export function formatMetricNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatMetricPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${value.toFixed(digits)}%`
}

export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}
