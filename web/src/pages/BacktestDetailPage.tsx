import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { backtestReportUrl, fetchBacktestDetail, fetchBacktestStatus } from '../api/backtests'
import { BacktestStatusChip, ReportStatusChip } from '../components/BacktestStatusChip'
import { BacktestConfigInspector } from '../components/BacktestConfigInspector'
import { BacktestRunChart } from '../components/BacktestRunChart'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { useSettings } from '../settings/useSettings'
import type { BacktestDetailResponse, BacktestRunResult, BacktestSelectionSummary } from '../types/backtests'
import { formatInTimezone } from '../utils/datetime'

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatTimestampOrDash(
  value: string | null | undefined,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  if (!value) {
    return '—'
  }
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function formatTimestamp(
  value: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  return formatInTimezone(value, timezone, timeDisplayFormat, true)
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toFixed(digits)
}

export function BacktestDetailPage() {
  const { platformSettings, appearance } = useSettings()
  const { backtestId = '' } = useParams()
  const [detail, setDetail] = useState<BacktestDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchBacktestDetail(backtestId)
        if (!cancelled) {
          setDetail(response)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load backtest detail')
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
  }, [backtestId])

  useEffect(() => {
    if (!detail) {
      return undefined
    }
    if (!['pending', 'running'].includes(detail.metadata.status)) {
      return undefined
    }

    const timer = window.setInterval(async () => {
      try {
        const status = await fetchBacktestStatus(backtestId)
        setDetail((current) =>
          current
            ? {
                ...current,
                metadata: status,
              }
            : current,
        )
        if (status.status === 'completed' || status.status === 'failed') {
          const nextDetail = await fetchBacktestDetail(backtestId)
          setDetail(nextDetail)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to refresh backtest status')
        window.clearInterval(timer)
      }
    }, platformSettings.platform_behavior.auto_refresh_interval_seconds * 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [backtestId, detail, platformSettings.platform_behavior.auto_refresh_interval_seconds])

  const metadata = detail?.metadata ?? null
  const report = detail?.report ?? null
  const progressValue = useMemo(() => {
    if (!metadata || metadata.total_runs === 0) {
      return 0
    }
    return (metadata.completed_runs / metadata.total_runs) * 100
  }, [metadata])

  if (loading) {
    return (
      <Stack sx={{ py: 10, alignItems: 'center' }} spacing={1}>
        <CircularProgress />
        <Typography color="text.secondary">Loading backtest detail…</Typography>
      </Stack>
    )
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>
  }

  if (!detail || !metadata) {
    return <Alert severity="warning">Backtest detail is unavailable.</Alert>
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={2}>
        <Button component={RouterLink} to="/backtests" startIcon={<ArrowBackIcon />} sx={{ width: 'fit-content' }}>
          Back to results
        </Button>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1}
          sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}
        >
          <Box>
            <Typography variant="h4">Backtest Analysis</Typography>
            <Typography color="text.secondary">
              Result id `{metadata.id}` created{' '}
              {formatTimestamp(
                metadata.created_at,
                platformSettings.platform_behavior.timezone,
                appearance.time_display_format,
              )}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <BacktestStatusChip status={metadata.status} />
            {metadata.report_status && <ReportStatusChip status={metadata.report_status} />}
          </Stack>
        </Stack>
      </Stack>

      {(metadata.status === 'pending' || metadata.status === 'running') && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={1.5}>
            <Typography variant="h6">Backtest in progress</Typography>
            <Typography color="text.secondary">
              {metadata.completed_runs} of {metadata.total_runs} runs completed.
            </Typography>
            <LinearProgress variant="determinate" value={progressValue} />
          </Stack>
        </Paper>
      )}

      {metadata.error_message && metadata.status === 'failed' && (
        <Alert severity="error">{metadata.error_message}</Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Submission summary</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
            <Metric label="Date range" value={`${metadata.selection.start_date} → ${metadata.selection.end_date}`} />
            <Metric label="Resolution" value={metadata.selection.resolution} />
            <Metric label="Symbols" value={metadata.selection.symbols.join(', ')} />
            <Metric label="Strategies" value={metadata.selection.strategies.join(', ')} />
          </Stack>
        </Stack>
      </Paper>

      {report ? (
        <>
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">Report overview</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                <Metric
                  label="Generated"
                  value={formatTimestamp(
                    report.generated_at,
                    platformSettings.platform_behavior.timezone,
                    appearance.time_display_format,
                  )}
                />
                <Metric label="Successful runs" value={String(report.successful_runs)} />
                <Metric label="Failed runs" value={String(report.failed_runs)} />
                <Metric label="Config hash" value={report.config_sha256.slice(0, 12)} />
                <Metric
                  label="Output JSON"
                  value={
                    detail.output_path ? (
                      <Link
                        href={backtestReportUrl(metadata.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        sx={{ wordBreak: 'break-all' }}
                      >
                        {metadata.id.slice(0, 8)}.json
                      </Link>
                    ) : (
                      'Pending write…'
                    )
                  }
                />
              </Stack>
            </Stack>
          </Paper>

          <BacktestConfigInspector
            backtestId={metadata.id}
            inputConfigPath={report.input_config_path}
            configSha256={report.config_sha256}
          />

          <Stack spacing={2}>
            {report.results.map((result, index) => (
              <RunResultCard
                key={result.run_id}
                result={result}
                selection={metadata.selection}
                defaultExpanded={index === 0}
              />
            ))}
          </Stack>
        </>
      ) : (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={1} sx={{ alignItems: 'center' }}>
            <Typography>No report payload available yet.</Typography>
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {label}
      </Typography>
      {typeof value === 'string' ? <Typography>{value}</Typography> : value}
    </Box>
  )
}

function RunResultCard({
  result,
  selection,
  defaultExpanded = false,
}: {
  result: BacktestRunResult
  selection: BacktestSelectionSummary
  defaultExpanded?: boolean
}) {
  const { platformSettings, appearance } = useSettings()
  const summary = result.summary
  const sortedTrades = [...result.trades].sort((left, right) => {
    const leftValue = left.datetime ? dayjs(left.datetime).valueOf() : Number.NEGATIVE_INFINITY
    const rightValue = right.datetime ? dayjs(right.datetime).valueOf() : Number.NEGATIVE_INFINITY
    return leftValue - rightValue
  })
  const sortedOrders = [...result.orders].sort((left, right) => {
    const leftValue = left.datetime ? dayjs(left.datetime).valueOf() : Number.NEGATIVE_INFINITY
    const rightValue = right.datetime ? dayjs(right.datetime).valueOf() : Number.NEGATIVE_INFINITY
    return leftValue - rightValue
  })
  const firstTrade = sortedTrades[0] ?? null
  const lastTrade = sortedTrades.at(-1) ?? null
  const latestOrders = [...sortedOrders].reverse().slice(0, 5)

  const runTitle = (
    <Stack spacing={0.25}>
      <Typography variant="h6">
        {result.symbol ?? 'Unknown symbol'} / {result.strategy}
      </Typography>
      {summary && (
        <Typography variant="body2" color="text.secondary">
          Return {formatPercent(summary.return_pct)} · Sharpe {summary.sharpe_ratio?.toFixed(2) ?? '—'} ·{' '}
          {summary.total_trades} trades
        </Typography>
      )}
    </Stack>
  )

  return (
    <CollapsibleSection
      defaultExpanded={defaultExpanded}
      title={runTitle}
      subtitle={result.name ?? result.run_id}
      actions={
        <BacktestStatusChip status={result.status === 'success' ? 'completed' : 'failed'} />
      }
    >
      <Stack spacing={2}>
        {result.error && <Alert severity="error">{result.error.message}</Alert>}

        {summary && (
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
            <Metric label="Return" value={formatPercent(summary.return_pct)} />
            <Metric label="Sharpe" value={summary.sharpe_ratio?.toFixed(2) ?? '—'} />
            <Metric label="Max drawdown" value={formatPercent(summary.max_drawdown_pct)} />
            <Metric label="Trades" value={String(summary.total_trades)} />
            <Metric label="Wins / losses" value={`${summary.won_trades} / ${summary.lost_trades}`} />
          </Stack>
        )}

        {result.status === 'success' && result.symbol && (
          <BacktestRunChart
            symbol={result.symbol}
            startDate={selection.start_date}
            endDate={selection.end_date}
            resolution={selection.resolution}
            orders={result.orders}
            trades={result.trades}
          />
        )}

        <Stack spacing={0.5}>
          <Typography variant="subtitle1">Trade activity</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
            <Metric label="Orders" value={String(result.orders.length)} />
            <Metric label="Trade records" value={String(result.trades.length)} />
            <Metric
              label="First trade"
              value={formatTimestampOrDash(
                firstTrade?.datetime,
                platformSettings.platform_behavior.timezone,
                appearance.time_display_format,
              )}
            />
            <Metric
              label="Last trade"
              value={formatTimestampOrDash(
                lastTrade?.datetime,
                platformSettings.platform_behavior.timezone,
                appearance.time_display_format,
              )}
            />
            <Metric label="Data source" value={result.data_source} />
          </Stack>
        </Stack>

        <CollapsibleSection
          title={`Trade records (${result.trades.length})`}
          defaultExpanded={sortedTrades.length > 0 && sortedTrades.length <= 10}
        >
          {result.trades.length > 0 ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>When</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Value</TableCell>
                  <TableCell align="right">PnL</TableCell>
                  <TableCell align="right">PnL after fees</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedTrades.map((trade, index) => (
                  <TableRow key={`${trade.datetime ?? 'no-datetime'}-${index}`}>
                    <TableCell>
                      {formatTimestampOrDash(
                        trade.datetime,
                        platformSettings.platform_behavior.timezone,
                        appearance.time_display_format,
                      )}
                    </TableCell>
                    <TableCell align="right">{formatNumber(trade.size, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(trade.price, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(trade.value, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(trade.pnl, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(trade.pnlcomm, 2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Typography color="text.secondary">No trade records were emitted for this run.</Typography>
          )}
        </CollapsibleSection>

        {latestOrders.length > 0 && (
          <CollapsibleSection title={`Recent orders (${latestOrders.length})`} defaultExpanded={false}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>When</TableCell>
                  <TableCell>Side</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Value</TableCell>
                  <TableCell align="right">Commission</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {latestOrders.map((order, index) => (
                  <TableRow key={`${order.datetime ?? 'no-datetime'}-${order.status}-${index}`}>
                    <TableCell>
                      {formatTimestampOrDash(
                        order.datetime,
                        platformSettings.platform_behavior.timezone,
                        appearance.time_display_format,
                      )}
                    </TableCell>
                    <TableCell>{order.is_buy ? 'Buy' : 'Sell'}</TableCell>
                    <TableCell>{order.status}</TableCell>
                    <TableCell align="right">{formatNumber(order.size, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(order.price, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(order.value, 2)}</TableCell>
                    <TableCell align="right">{formatNumber(order.commission, 2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CollapsibleSection>
        )}
      </Stack>
    </CollapsibleSection>
  )
}
