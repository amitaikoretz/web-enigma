import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import LaunchIcon from '@mui/icons-material/Launch'
import {
  Alert,
  Button,
  IconButton,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fetchBacktestTradeReplayCapsule } from '../api/backtests'
import type { BacktestTradeRecord } from '../types/backtests'
import { type SortDirection, type SortableTableColumn, sortRows } from './SortableTradeRecordsTable'
import { formatInTimezone } from '../utils/datetime'
import {
  TRADE_PAGE_SIZE_OPTIONS,
  TRADE_PAGE_PARAM,
  TRADE_PAGE_SIZE_PARAM,
  TRADE_SEARCH_PARAM,
  parseTradeRecordsViewState,
  tradeRecordsViewStateToSearchParams,
} from '../utils/tradeRecords'
import { buildTradeChartFocusWindowMs } from '../utils/backtestChartFocus'

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toFixed(digits)
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

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase()
}

function buildReplayLaunchConfigWithInheritedAlpacaEnv(
  launchConfig: Record<string, unknown>,
): Record<string, unknown> {
  const env = {
    ...(typeof launchConfig.env === 'object' && launchConfig.env !== null ? (launchConfig.env as Record<string, unknown>) : {}),
    ALPACA_API_KEY: '${env:ALPACA_API_KEY}',
    ALPACA_SECRET_KEY: '${env:ALPACA_SECRET_KEY}',
  }
  return {
    ...launchConfig,
    env,
  }
}

function buildTradeSearchHaystack(
  trade: BacktestTradeRecord,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  const fragments: unknown[] = [
    trade.datetime,
    trade.size,
    trade.price,
    trade.value,
    trade.pnl,
    trade.pnlcomm,
    trade.reason,
    trade.entry_datetime,
    trade.hold_minutes,
    trade.hold_bars,
  ]

  if (trade.datetime) {
    fragments.push(formatTimestampOrDash(trade.datetime, timezone, timeDisplayFormat))
  }
  if (trade.entry_datetime) {
    fragments.push(formatTimestampOrDash(trade.entry_datetime, timezone, timeDisplayFormat))
  }

  return fragments
    .filter((fragment): fragment is string | number => fragment !== null && fragment !== undefined)
    .map((fragment) => String(fragment).toLowerCase())
    .join(' ')
}

interface BacktestTradeRecordsTableProps {
  backtestId: string
  runId: string
  trades: BacktestTradeRecord[]
  timezone: string
  timeDisplayFormat: '12h' | '24h'
  onFocusChartTrade?: (trade: BacktestTradeRecord) => void
}

export function BacktestTradeRecordsTable({
  backtestId,
  runId,
  trades,
  timezone,
  timeDisplayFormat,
  onFocusChartTrade,
}: BacktestTradeRecordsTableProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const viewState = useMemo(() => parseTradeRecordsViewState(searchParams), [searchParams])
  const [sortKey, setSortKey] = useState('datetime')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [replayNotice, setReplayNotice] = useState<{ message: string; severity: 'success' | 'error' } | null>(null)
  const [replayLoadingKey, setReplayLoadingKey] = useState<string | null>(null)

  const columns = useMemo<Array<SortableTableColumn<BacktestTradeRecord>>>(() => {
    return [
      {
        id: 'datetime',
        label: 'When',
        defaultSortDirection: 'asc',
        sortValue: (trade) => {
          if (!trade.datetime) {
            return null
          }
          const parsed = Date.parse(trade.datetime)
          return Number.isNaN(parsed) ? null : parsed
        },
        render: (trade) => formatTimestampOrDash(trade.datetime, timezone, timeDisplayFormat),
      },
      {
        id: 'size',
        label: 'Size',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.size,
        render: (trade) => formatNumber(trade.size, 2),
      },
      {
        id: 'price',
        label: 'Price',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.price,
        render: (trade) => formatNumber(trade.price, 2),
      },
      {
        id: 'value',
        label: 'Value',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.value,
        render: (trade) => formatNumber(trade.value, 2),
      },
      {
        id: 'pnl',
        label: 'PnL',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.pnl,
        render: (trade) => formatNumber(trade.pnl, 2),
      },
      {
        id: 'pnlcomm',
        label: 'PnL after fees',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.pnlcomm,
        render: (trade) => formatNumber(trade.pnlcomm, 2),
      },
      {
        id: 'reason',
        label: 'Exit',
        sortValue: (trade) => trade.reason ?? '',
        render: (trade) => trade.reason ?? '—',
      },
      {
        id: 'hold_minutes',
        label: 'Hold (min)',
        align: 'right',
        defaultSortDirection: 'desc',
        sortValue: (trade) => trade.hold_minutes,
        render: (trade) => formatNumber(trade.hold_minutes, 1),
      },
    ]
  }, [timeDisplayFormat, timezone])

  const filteredTrades = useMemo(() => {
    const query = normalizeSearch(viewState.search)
    if (!query) {
      return trades
    }

    return trades.filter((trade) => buildTradeSearchHaystack(trade, timezone, timeDisplayFormat).includes(query))
  }, [timeDisplayFormat, timezone, trades, viewState.search])

  const sortedTrades = useMemo(
    () => sortRows(filteredTrades, columns, sortKey, sortDirection),
    [columns, filteredTrades, sortDirection, sortKey],
  )

  const totalPages = Math.max(1, Math.ceil(filteredTrades.length / viewState.pageSize))
  const currentPage = Math.min(viewState.page, totalPages)
  const startIndex = filteredTrades.length === 0 ? 0 : (currentPage - 1) * viewState.pageSize
  const pageTrades = sortedTrades.slice(startIndex, startIndex + viewState.pageSize)
  const showingStart = filteredTrades.length === 0 ? 0 : startIndex + 1
  const showingEnd = filteredTrades.length === 0 ? 0 : Math.min(startIndex + viewState.pageSize, filteredTrades.length)

  useEffect(() => {
    if (currentPage === viewState.page) {
      return
    }

    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete(TRADE_PAGE_PARAM)
    nextParams.delete(TRADE_PAGE_SIZE_PARAM)
    nextParams.delete(TRADE_SEARCH_PARAM)
    for (const [key, value] of tradeRecordsViewStateToSearchParams({
      page: currentPage,
      pageSize: viewState.pageSize,
      search: viewState.search,
    })) {
      nextParams.set(key, value)
    }
    setSearchParams(nextParams, { replace: true })
  }, [currentPage, searchParams, setSearchParams, viewState.page, viewState.pageSize, viewState.search])

  function updateViewState(partial: Partial<typeof viewState>) {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete(TRADE_PAGE_PARAM)
    nextParams.delete(TRADE_PAGE_SIZE_PARAM)
    nextParams.delete(TRADE_SEARCH_PARAM)

    const nextState = {
      page: partial.page ?? viewState.page,
      pageSize: partial.pageSize ?? viewState.pageSize,
      search: partial.search ?? viewState.search,
    }

    for (const [key, value] of tradeRecordsViewStateToSearchParams(nextState)) {
      nextParams.set(key, value)
    }

    setSearchParams(nextParams, { replace: true })
  }

  const handleSort = (column: SortableTableColumn<BacktestTradeRecord>) => {
    if (sortKey === column.id) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }

    setSortKey(column.id)
    setSortDirection(column.defaultSortDirection ?? 'asc')
  }

  async function handleCopyReplayConfig(trade: BacktestTradeRecord, tradeIndex: number) {
    const tradeKey = `${trade.datetime ?? 'no-datetime'}-${trade.entry_datetime ?? 'no-entry'}-${tradeIndex}`
    setReplayLoadingKey(tradeKey)
    try {
      const response = await fetchBacktestTradeReplayCapsule(backtestId, runId, tradeIndex)
      const launchConfig = buildReplayLaunchConfigWithInheritedAlpacaEnv(response.launch_config)
      await navigator.clipboard.writeText(JSON.stringify(launchConfig, null, 2))
      setReplayNotice({
        message: 'Copied replay debug config to clipboard.',
        severity: 'success',
      })
    } catch (error) {
      setReplayNotice({
        message: error instanceof Error ? error.message : 'Failed to copy replay debug config.',
        severity: 'error',
      })
    } finally {
      setReplayLoadingKey(null)
    }
  }

  const hasTrades = trades.length > 0
  const hasMatches = filteredTrades.length > 0
  const searchValue = viewState.search
  const hasSearch = normalizeSearch(searchValue).length > 0

  if (!hasTrades) {
    return <Typography color="text.secondary">No trade records were emitted for this run.</Typography>
  }

  return (
    <Stack spacing={1.5}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' } }}>
        <TextField
          fullWidth
          label="Search trade records"
          value={searchValue}
          onChange={(event) => updateViewState({ search: event.target.value, page: 1 })}
          placeholder="Timestamp, price, PnL, exit reason..."
        />
        {hasSearch && (
          <Button
            variant="outlined"
            onClick={() => updateViewState({ search: '', page: 1 })}
          >
            Clear
          </Button>
        )}
      </Stack>

      <Typography variant="body2" color="text.secondary">
        {hasMatches
          ? `Showing ${showingStart}-${showingEnd} of ${filteredTrades.length} trade records`
          : `Showing 0 of ${trades.length} trade records`}
      </Typography>

      {!hasMatches ? (
        <Typography color="text.secondary">No trade records match the current search.</Typography>
      ) : (
        <>
          <Table size="small">
            <TableHead>
              <TableRow>
                {columns.map((column) => {
                  const active = sortKey === column.id
                  return (
                    <TableCell key={column.id} align={column.align} sortDirection={active ? sortDirection : false}>
                      <TableSortLabel
                        active={active}
                        direction={active ? sortDirection : column.defaultSortDirection ?? 'asc'}
                        onClick={() => handleSort(column)}
                      >
                        {column.label}
                      </TableSortLabel>
                    </TableCell>
                  )
                })}
                <TableCell padding="checkbox" />
              </TableRow>
            </TableHead>
            <TableBody>
              {pageTrades.map((trade, index) => {
                const focusWindow = buildTradeChartFocusWindowMs(trade)
                const tradeIndex = trades.indexOf(trade)
                const tradeKey = `${trade.datetime ?? 'no-datetime'}-${trade.entry_datetime ?? 'no-entry'}-${tradeIndex}`
                const replayDisabled = !trade.entry_datetime && !trade.datetime
                const replayLoading = replayLoadingKey === tradeKey
                let activated = false
                const handleOpenChart = () => {
                  if (activated) {
                    return
                  }
                  activated = true
                  onFocusChartTrade?.(trade)
                }

                return (
                  <TableRow
                    key={[
                      trade.datetime ?? 'no-datetime',
                      trade.entry_datetime ?? 'no-entry-datetime',
                      trade.size,
                      trade.price,
                      trade.pnlcomm,
                      trade.reason ?? 'no-reason',
                      startIndex + index,
                    ].join('-')}
                    hover
                  >
                    {columns.map((column) => (
                      <TableCell key={column.id} align={column.align}>
                        {column.render(trade, startIndex + index)}
                      </TableCell>
                    ))}
                    <TableCell padding="checkbox" sx={{ whiteSpace: 'nowrap' }}>
                      <Stack direction="row" spacing={0.25} sx={{ alignItems: 'center' }}>
                        <Tooltip
                          title={
                            focusWindow
                              ? 'Show chart for this trade'
                              : 'This trade does not have enough timestamps to open the chart'
                          }
                        >
                          <span>
                            <button
                              type="button"
                              aria-label="Open chart for trade"
                              title={
                                focusWindow
                                  ? 'Show chart for this trade'
                                  : 'This trade does not have enough timestamps to open the chart'
                              }
                              disabled={!onFocusChartTrade || !focusWindow}
                              onMouseUp={handleOpenChart}
                              onPointerUp={handleOpenChart}
                              onClick={handleOpenChart}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: 28,
                                height: 28,
                                padding: 0,
                                margin: 0,
                                color: 'inherit',
                                background: 'transparent',
                                border: 'none',
                                borderRadius: 4,
                                cursor: 'pointer',
                              }}
                            >
                              <LaunchIcon fontSize="small" />
                            </button>
                          </span>
                        </Tooltip>
                        <Tooltip
                          title={
                            replayDisabled
                              ? 'This trade does not have enough timestamps to build a replay capsule'
                              : 'Copy replay debug config'
                          }
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label="Copy replay debug config"
                              disabled={replayDisabled || replayLoading || !backtestId || !runId}
                              onClick={() => {
                                void handleCopyReplayConfig(trade, tradeIndex)
                              }}
                            >
                              <ContentCopyIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>

          <TablePagination
            component="div"
            count={filteredTrades.length}
            page={currentPage - 1}
            rowsPerPage={viewState.pageSize}
            rowsPerPageOptions={TRADE_PAGE_SIZE_OPTIONS}
            onPageChange={(_event, nextPage) => updateViewState({ page: nextPage + 1 })}
            onRowsPerPageChange={(event) => updateViewState({ page: 1, pageSize: Number(event.target.value) })}
          />
        </>
      )}
      {replayNotice ? (
        <Snackbar
          open
          autoHideDuration={3000}
          onClose={() => setReplayNotice(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert severity={replayNotice.severity} variant="filled" onClose={() => setReplayNotice(null)}>
            {replayNotice.message}
          </Alert>
        </Snackbar>
      ) : null}
    </Stack>
  )
}
