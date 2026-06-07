import { Alert, Box, Chip, Paper, Stack, Typography } from '@mui/material'

import type { FeatureImportanceTarget } from '../types/modelFamilies'

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function FeatureImportanceTab({
  target,
  targets,
}: {
  target?: FeatureImportanceTarget | null
  targets?: FeatureImportanceTarget[] | null
}) {
  const resolvedTargets = targets ?? (target ? [target] : [])
  if (resolvedTargets.length === 0) {
    return <Alert severity="info">No persisted feature-importance artifact is available yet.</Alert>
  }

  return (
    <Stack spacing={1.5}>
      {resolvedTargets.map((item) => (
        <Paper key={item.target_key} variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
          <Stack spacing={1.25}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {item.target_key}
              </Typography>
              <Chip size="small" label={`${item.rows.length} features`} variant="outlined" />
            </Stack>
            {item.rows.length === 0 ? (
              <Typography color="text.secondary" variant="body2">
                No feature importances were recorded for this target.
              </Typography>
            ) : (
              <Stack spacing={1}>
                {item.rows.slice(0, 20).map((row) => (
                  <Stack key={row.feature} spacing={0.5}>
                    <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 0 }}>
                        {row.feature}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                        {formatPercent(row.importance)}
                      </Typography>
                    </Stack>
                    <Box
                      sx={{
                        height: 10,
                        borderRadius: 999,
                        bgcolor: 'action.hover',
                        overflow: 'hidden',
                      }}
                    >
                      <Box
                        sx={{
                          height: '100%',
                          width: `${Math.max(0, Math.min(100, row.importance * 100))}%`,
                          borderRadius: 999,
                          background:
                            'linear-gradient(90deg, rgba(25,118,210,0.95) 0%, rgba(37,99,235,0.8) 100%)',
                        }}
                      />
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      {row.signed_importance == null ? 'Absolute importance' : `Signed coefficient ${row.signed_importance.toFixed(4)}`}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            )}
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}
