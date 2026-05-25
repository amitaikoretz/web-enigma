import { Box, Paper, Stack, Typography } from '@mui/material'

import type { BacktestRunResult, PortfolioAggregate } from '../types/backtests'
import { formatSignedPercent } from '../utils/backtestAggregates'
import { formatMetricNumber, pnlTone } from './BacktestMetricGrid'

interface BacktestSummaryDashboardProps {
  portfolio: PortfolioAggregate | null
  results: BacktestRunResult[]
  bestRunId: string | null
  worstRunId: string | null
}

function HighlightCard({
  kind,
  label,
  title,
  value,
  tone,
}: {
  kind: 'best' | 'worst' | 'failures'
  label: string
  title: string
  value: string
  tone?: 'positive' | 'negative' | 'default'
}) {
  const bgcolor =
    kind === 'best' ? 'success.50' : kind === 'worst' ? 'error.50' : 'warning.50'
  const borderColor =
    kind === 'best' ? 'success.light' : kind === 'worst' ? 'error.light' : 'warning.light'

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor,
        borderColor,
        height: '100%',
      }}
    >
      <Typography variant="overline" color="text.secondary" sx={{ display: 'block' }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        {title}
      </Typography>
      <Typography
        variant="h6"
        sx={{
          mt: 0.75,
          color:
            tone === 'positive'
              ? 'success.main'
              : tone === 'negative'
                ? 'error.main'
                : 'text.primary',
        }}
      >
        {value}
      </Typography>
    </Paper>
  )
}

function runLabel(result: BacktestRunResult | undefined): string {
  if (!result) {
    return '—'
  }
  return `${result.symbol ?? 'Unknown'} / ${result.strategy}`
}

export function BacktestSummaryDashboard({
  portfolio,
  results,
  bestRunId,
  worstRunId,
}: BacktestSummaryDashboardProps) {
  if (!portfolio) {
    return null
  }

  const bestRun = results.find((result) => result.run_id === bestRunId)
  const worstRun = results.find((result) => result.run_id === worstRunId)
  const failedCount = results.filter((result) => result.status === 'failed').length

  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(5, minmax(0, 1fr))' },
          gap: 2,
        }}
      >
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="overline" color="text.secondary">
            Portfolio net PnL
          </Typography>
          <Typography variant="h5" sx={{ color: pnlTone(portfolio.total_net_pnl) === 'positive' ? 'success.main' : portfolio.total_net_pnl < 0 ? 'error.main' : undefined }}>
            {formatMetricNumber(portfolio.total_net_pnl)}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="overline" color="text.secondary">
            Combined return
          </Typography>
          <Typography variant="h5">{formatSignedPercent(portfolio.combined_return_pct)}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="overline" color="text.secondary">
            Total trades
          </Typography>
          <Typography variant="h5">{portfolio.total_trades}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="overline" color="text.secondary">
            Win rate
          </Typography>
          <Typography variant="h5">
            {portfolio.win_rate_pct != null ? `${portfolio.win_rate_pct.toFixed(1)}%` : '—'}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="overline" color="text.secondary">
            Wins / losses
          </Typography>
          <Typography variant="h5">
            {portfolio.won_trades} / {portfolio.lost_trades}
          </Typography>
        </Paper>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' },
          gap: 2,
        }}
      >
        <HighlightCard
          kind="best"
          label="Best run"
          title={runLabel(bestRun)}
          value={formatSignedPercent(bestRun?.summary?.return_pct)}
          tone="positive"
        />
        <HighlightCard
          kind="worst"
          label="Worst run"
          title={runLabel(worstRun)}
          value={formatSignedPercent(worstRun?.summary?.return_pct)}
          tone="negative"
        />
        <HighlightCard
          kind="failures"
          label="Failed runs"
          title={failedCount === 0 ? 'None in this batch' : `${failedCount} failed run${failedCount === 1 ? '' : 's'}`}
          value={`${results.length - failedCount} / ${results.length} OK`}
        />
      </Box>
    </Stack>
  )
}
