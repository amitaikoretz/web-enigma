import RestartAltIcon from '@mui/icons-material/RestartAlt'
import ZoomInMapIcon from '@mui/icons-material/ZoomInMap'
import { Box, IconButton, Stack, ToggleButton, Tooltip, Typography, useTheme } from '@mui/material'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useSettings } from '../settings/useSettings'
import type { OrderRecord, TradeRecord } from '../types/dayBacktest'
import type { MarketDataResponse } from '../types/marketData'
import { clampTradeChartFocusWindowMs, type TradeChartFocusWindowMs } from '../utils/backtestChartFocus'
import {
  chartTimeToMs,
  msToChartTime,
  toChartTime,
  createChartTimeFormatter,
  createChartTickMarkFormatter,
} from '../utils/chartTime'
import { getTradingDayBoundaryTimes } from '../utils/tradingDayBoundaries'
import { ChartViewportWindow } from './ChartViewportWindow'

export type ChartThemeMode = 'light' | 'dark'

interface CandlestickChartProps {
  data: MarketDataResponse | null
  orders?: OrderRecord[]
  trades?: TradeRecord[]
  annotationMarkers?: SeriesMarker<Time>[]
  focusWindow?: TradeChartFocusWindowMs | null
  onResetFocusWindow?: () => void
  showViewportWindow?: boolean
  themeMode?: ChartThemeMode
}

const BUY_MARKER_COLOR = '#58a6ff'
const SELL_MARKER_COLOR = '#f0883e'
const WIN_TRADE_COLOR = '#3fb950'
const LOSS_TRADE_COLOR = '#f85149'
const MIN_SELECTION_PX = 8
const VOLUME_PANE_STRETCH = 0.28

const CHART_THEME: Record<
  ChartThemeMode,
  {
    background: string
    border: string
    controlBackground: string
    controlBorder: string
    grid: string
    labelBackground: string
    mutedText: string
    paneSeparator: string
    paneSeparatorHover: string
    dayBoundary: string
    selectionBackground: string
    selectionBorder: string
    text: string
    tooltipBackground: string
    tooltipBorder: string
    tooltipText: string
  }
> = {
  dark: {
    background: '#0d1117',
    border: '#30363d',
    controlBackground: 'rgba(22, 27, 34, 0.88)',
    controlBorder: '#30363d',
    grid: '#30363d',
    labelBackground: '#30363d',
    mutedText: '#c9d1d9',
    paneSeparator: '#30363d',
    paneSeparatorHover: '#484f58',
    dayBoundary: 'rgba(148, 163, 184, 0.35)',
    selectionBackground: 'rgba(88, 166, 255, 0.12)',
    selectionBorder: 'rgba(88, 166, 255, 0.55)',
    text: '#f0f6fc',
    tooltipBackground: 'rgba(22, 27, 34, 0.96)',
    tooltipBorder: '#30363d',
    tooltipText: '#c9d1d9',
  },
  light: {
    background: '#ffffff',
    border: '#d0d7de',
    controlBackground: 'rgba(255, 255, 255, 0.92)',
    controlBorder: '#d0d7de',
    grid: '#e5e7eb',
    labelBackground: '#64748b',
    mutedText: '#4b5563',
    paneSeparator: '#d0d7de',
    paneSeparatorHover: '#94a3b8',
    dayBoundary: 'rgba(100, 116, 139, 0.35)',
    selectionBackground: 'rgba(37, 99, 235, 0.10)',
    selectionBorder: 'rgba(37, 99, 235, 0.45)',
    text: '#0f172a',
    tooltipBackground: 'rgba(255, 255, 255, 0.98)',
    tooltipBorder: '#d0d7de',
    tooltipText: '#111827',
  },
}

function toCandlestickData(data: MarketDataResponse): CandlestickData<Time>[] {
  return data.rows.map((row) => ({
    time: toChartTime(row.timestamp, data.resolution),
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
  }))
}

function toVolumeData(
  data: MarketDataResponse,
  upColor: string,
  downColor: string,
): HistogramData<Time>[] {
  return data.rows.map((row) => ({
    time: toChartTime(row.timestamp, data.resolution),
    value: row.volume,
    color: row.close >= row.open ? upColor : downColor,
  }))
}

function formatVolume(volume: number): string {
  if (volume >= 1_000_000) {
    return `${(volume / 1_000_000).toFixed(1)}M`
  }
  if (volume >= 1_000) {
    return `${(volume / 1_000).toFixed(1)}K`
  }
  return volume.toFixed(0)
}

function indexOrdersByTime(data: MarketDataResponse, orders: OrderRecord[]): Map<string, OrderRecord[]> {
  const barTimes = new Set(data.rows.map((row) => String(toChartTime(row.timestamp, data.resolution))))
  const byTime = new Map<string, OrderRecord[]>()

  for (const order of orders) {
    if (!order.datetime) {
      continue
    }
    const timeKey = String(toChartTime(order.datetime, data.resolution))
    if (!barTimes.has(timeKey)) {
      continue
    }
    const existing = byTime.get(timeKey) ?? []
    existing.push(order)
    byTime.set(timeKey, existing)
  }

  return byTime
}

function formatTradePnl(pnl: number): string {
  const sign = pnl >= 0 ? '+' : ''
  return `${sign}${pnl.toFixed(0)}`
}

function toTradeMarkers(data: MarketDataResponse, trades: TradeRecord[]): SeriesMarker<Time>[] {
  const barTimes = new Set(data.rows.map((row) => String(toChartTime(row.timestamp, data.resolution))))
  const markers: SeriesMarker<Time>[] = []

  for (const trade of trades) {
    if (!trade.datetime) {
      continue
    }
    const time = toChartTime(trade.datetime, data.resolution)
    if (!barTimes.has(String(time))) {
      continue
    }
    const isWin = trade.pnlcomm >= 0
    markers.push({
      time,
      position: 'inBar',
      color: isWin ? WIN_TRADE_COLOR : LOSS_TRADE_COLOR,
      shape: 'circle',
      text: formatTradePnl(trade.pnlcomm),
    })
  }

  return markers
}

function toAnnotationMarkers(
  data: MarketDataResponse,
  orders: OrderRecord[],
  trades: TradeRecord[],
  annotationMarkers: SeriesMarker<Time>[] = [],
): SeriesMarker<Time>[] {
  const barTimes = new Set(data.rows.map((row) => String(toChartTime(row.timestamp, data.resolution))))
  const markers: SeriesMarker<Time>[] = []

  for (const order of orders) {
    if (!order.datetime) {
      continue
    }
    const time = toChartTime(order.datetime, data.resolution)
    if (!barTimes.has(String(time))) {
      continue
    }
    markers.push({
      time,
      position: order.is_buy ? 'belowBar' : 'aboveBar',
      color: order.is_buy ? BUY_MARKER_COLOR : SELL_MARKER_COLOR,
      shape: order.is_buy ? 'arrowUp' : 'arrowDown',
      text: order.is_buy ? 'B' : 'S',
    })
  }

  markers.push(...toTradeMarkers(data, trades))
  markers.push(...annotationMarkers.filter((marker) => barTimes.has(String(marker.time))))
  return markers.sort((left, right) => Number(left.time) - Number(right.time))
}

function formatBarTime(
  timestamp: string,
  resolution: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  if (resolution === '1d') {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(timestamp))
  }
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: timeDisplayFormat === '12h',
  }).format(new Date(timestamp))
}

function formatOrderLine(order: OrderRecord): string {
  const side = order.is_buy ? 'Buy' : 'Sell'
  const sideColor = order.is_buy ? BUY_MARKER_COLOR : SELL_MARKER_COLOR
  return `<div style="color:${sideColor};font-weight:600">${side} ${order.size} @ $${order.price.toFixed(2)}</div>`
}

function formatTradeLine(trade: TradeRecord): string {
  const isWin = trade.pnlcomm >= 0
  const color = isWin ? WIN_TRADE_COLOR : LOSS_TRADE_COLOR
  return `<div style="color:${color};font-weight:600">Close ${trade.size} @ $${trade.price.toFixed(2)} · PnL ${formatTradePnl(trade.pnlcomm)}</div>`
}

function indexTradesByTime(data: MarketDataResponse, trades: TradeRecord[]): Map<string, TradeRecord[]> {
  const barTimes = new Set(data.rows.map((row) => String(toChartTime(row.timestamp, data.resolution))))
  const byTime = new Map<string, TradeRecord[]>()

  for (const trade of trades) {
    if (!trade.datetime) {
      continue
    }
    const timeKey = String(toChartTime(trade.datetime, data.resolution))
    if (!barTimes.has(timeKey)) {
      continue
    }
    const existing = byTime.get(timeKey) ?? []
    existing.push(trade)
    byTime.set(timeKey, existing)
  }

  return byTime
}

function buildTooltipHtml(
  bar: { open: number; high: number; low: number; close: number; volume: number; timestamp: string },
  resolution: string,
  ordersAtBar: OrderRecord[],
  tradesAtBar: TradeRecord[],
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
  borderColor: string,
): string {
  const lines = [
    `<div style="font-weight:600;margin-bottom:4px">${formatBarTime(bar.timestamp, resolution, timezone, timeDisplayFormat)}</div>`,
    `<div>O ${bar.open.toFixed(2)} &nbsp; H ${bar.high.toFixed(2)} &nbsp; L ${bar.low.toFixed(2)} &nbsp; C ${bar.close.toFixed(2)}</div>`,
    `<div style="margin-top:4px">Vol ${formatVolume(bar.volume)}</div>`,
  ]

  if (ordersAtBar.length > 0 || tradesAtBar.length > 0) {
    lines.push(`<div style="margin-top:6px;border-top:1px solid ${borderColor};padding-top:6px">`)
    lines.push(ordersAtBar.map(formatOrderLine).join(''))
    lines.push(tradesAtBar.map(formatTradeLine).join(''))
    lines.push('</div>')
  }

  return lines.join('')
}

export function CandlestickChart({
  data,
  orders = [],
  trades = [],
  annotationMarkers = [],
  focusWindow = null,
  onResetFocusWindow,
  showViewportWindow = false,
  themeMode,
}: CandlestickChartProps) {
  const { appearance, platformSettings } = useSettings()
  const theme = useTheme()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const selectionRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const dataRef = useRef(data)
  const ordersRef = useRef(orders)
  const tradesRef = useRef(trades)
  const zoomSelectModeRef = useRef(false)
  const selectingRef = useRef<{ startX: number; pointerId: number } | null>(null)

  const [zoomSelectMode, setZoomSelectMode] = useState(false)
  const [chartInstance, setChartInstance] = useState<IChartApi | null>(null)
  const [boundaryPositions, setBoundaryPositions] = useState<number[]>([])
  const resolvedThemeMode: ChartThemeMode = themeMode ?? (theme.palette.mode === 'light' ? 'light' : 'dark')
  const chartTheme = CHART_THEME[resolvedThemeMode]
  const dataRange = useMemo(() => {
    if (!data || data.rows.length === 0) {
      return null
    }

    return {
      from: toChartTime(data.rows[0].timestamp, data.resolution),
      to: toChartTime(data.rows.at(-1)!.timestamp, data.resolution),
    }
  }, [data])
  const boundaryTimes = useMemo(
    () => (data ? getTradingDayBoundaryTimes(data, platformSettings.platform_behavior.timezone) : []),
    [data, platformSettings.platform_behavior.timezone],
  )
  const focusRange = useMemo(() => {
    if (!data || !focusWindow || !dataRange || data.resolution === '1d') {
      return null
    }

    const clamped = clampTradeChartFocusWindowMs(focusWindow, {
      fromMs: chartTimeToMs(dataRange.from),
      toMs: chartTimeToMs(dataRange.to),
    })

    if (!clamped) {
      return null
    }

    return {
      from: msToChartTime(clamped.fromMs, data.resolution),
      to: msToChartTime(clamped.toMs, data.resolution),
    }
  }, [data, dataRange, focusWindow])

  const updateBoundaryPositions = useCallback(() => {
    const chart = chartRef.current
    if (!chart || boundaryTimes.length === 0) {
      setBoundaryPositions([])
      return
    }

    const timeScale = chart.timeScale()
    const nextPositions = boundaryTimes
      .map((time) => timeScale.timeToCoordinate(time))
      .filter((coordinate): coordinate is NonNullable<typeof coordinate> => coordinate !== null)
      .map((coordinate) => Number(coordinate))

    setBoundaryPositions((current) => {
      if (
        current.length === nextPositions.length &&
        current.every((value, index) => value === nextPositions[index])
      ) {
        return current
      }
      return nextPositions
    })
  }, [boundaryTimes])

  useEffect(() => {
    dataRef.current = data
    ordersRef.current = orders
    tradesRef.current = trades
  }, [data, orders, trades])

  useEffect(() => {
    zoomSelectModeRef.current = zoomSelectMode
    chartRef.current?.applyOptions({
      handleScroll: {
        pressedMouseMove: !zoomSelectMode,
      },
    })
  }, [zoomSelectMode])

  const resetZoom = useCallback(() => {
    chartRef.current?.timeScale().fitContent()
    onResetFocusWindow?.()
  }, [onResetFocusWindow])

  useEffect(() => {
    const container = chartContainerRef.current
    const wrapper = wrapperRef.current
    if (!container || !wrapper) {
      return
    }

    const chart = createChart(container, {
      layout: {
        background: {
          type: ColorType.Solid,
          color: chartTheme.background,
        },
        textColor: appearance.indicator_contrast === 'high' ? chartTheme.text : chartTheme.mutedText,
        panes: {
          separatorColor: appearance.indicator_contrast === 'high' ? chartTheme.paneSeparatorHover : chartTheme.paneSeparator,
          separatorHoverColor:
            appearance.indicator_contrast === 'high'
              ? chartTheme.paneSeparatorHover
              : chartTheme.paneSeparatorHover,
          enableResize: true,
        },
      },
      grid: {
        vertLines: { color: appearance.chart_grid_visible ? chartTheme.grid : 'transparent' },
        horzLines: { color: appearance.chart_grid_visible ? chartTheme.grid : 'transparent' },
      },
      rightPriceScale: {
        borderColor: chartTheme.border,
      },
      timeScale: {
        borderColor: chartTheme.border,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: createChartTickMarkFormatter(
          platformSettings.platform_behavior.timezone,
          appearance.time_display_format,
        ),
      },
      localization: {
        timeFormatter: createChartTimeFormatter(
          platformSettings.platform_behavior.timezone,
          appearance.time_display_format,
        ),
      },
      crosshair: {
        vertLine: { labelBackgroundColor: chartTheme.labelBackground },
        horzLine: { labelBackgroundColor: chartTheme.labelBackground },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisDoubleClickReset: {
          time: true,
          price: true,
        },
      },
      width: container.clientWidth,
      height: container.clientHeight,
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: appearance.chart_up_color,
      downColor: appearance.chart_down_color,
      borderVisible: false,
      wickUpColor: appearance.chart_up_color,
      wickDownColor: appearance.chart_down_color,
    })

    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: 'volume' },
        lastValueVisible: false,
        priceLineVisible: false,
      },
      1,
    )
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.08, bottom: 0 },
    })

    const panes = chart.panes()
    panes[0]?.setStretchFactor(1 - VOLUME_PANE_STRETCH)
    panes[1]?.setStretchFactor(VOLUME_PANE_STRETCH)

    chartRef.current = chart
    setChartInstance(chart)
    seriesRef.current = series
    volumeSeriesRef.current = volumeSeries
    markersRef.current = createSeriesMarkers(series, [])

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      const tooltip = tooltipRef.current
      const chartData = dataRef.current
      if (!tooltip || !chartData) {
        return
      }

      if (
        param.point === undefined ||
        param.time === undefined ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        tooltip.style.display = 'none'
        return
      }

      const timeKey = String(param.time)
      const row = chartData.rows.find(
        (entry) => String(toChartTime(entry.timestamp, chartData.resolution)) === timeKey,
      )
      if (!row) {
        tooltip.style.display = 'none'
        return
      }

      const ordersAtBar = indexOrdersByTime(chartData, ordersRef.current).get(timeKey) ?? []
      const tradesAtBar = indexTradesByTime(chartData, tradesRef.current).get(timeKey) ?? []
      tooltip.innerHTML = buildTooltipHtml(
        row,
        chartData.resolution,
        ordersAtBar,
        tradesAtBar,
        platformSettings.platform_behavior.timezone,
        appearance.time_display_format,
        chartTheme.tooltipBorder,
      )
      tooltip.style.display = 'block'

      const margin = 12
      const tooltipWidth = tooltip.offsetWidth
      const tooltipHeight = tooltip.offsetHeight
      const left = Math.min(
        param.point.x + margin,
        wrapper.clientWidth - tooltipWidth - margin,
      )
      const top = Math.max(
        margin,
        Math.min(param.point.y - tooltipHeight - margin, wrapper.clientHeight - tooltipHeight - margin),
      )
      tooltip.style.left = `${left}px`
      tooltip.style.top = `${top}px`
    }

    chart.subscribeCrosshairMove(onCrosshairMove)
    const timeScale = chart.timeScale()
    const onVisibleTimeRangeChange = () => {
      updateBoundaryPositions()
    }
    timeScale.subscribeVisibleTimeRangeChange(onVisibleTimeRangeChange)

    const hideSelection = () => {
      const selection = selectionRef.current
      if (selection) {
        selection.style.display = 'none'
      }
    }

    const updateSelection = (startX: number, currentX: number) => {
      const selection = selectionRef.current
      if (!selection) {
        return
      }
      const left = Math.min(startX, currentX)
      const width = Math.abs(currentX - startX)
      selection.style.display = 'block'
      selection.style.left = `${left}px`
      selection.style.width = `${width}px`
    }

    const finishSelection = (startX: number, endX: number) => {
      hideSelection()
      if (Math.abs(endX - startX) < MIN_SELECTION_PX) {
        return
      }

      const timeScale = chart.timeScale()
      const chartWidth = timeScale.width()
      const fromX = Math.max(0, Math.min(Math.min(startX, endX), chartWidth))
      const toX = Math.max(0, Math.min(Math.max(startX, endX), chartWidth))

      const fromLogical = timeScale.coordinateToLogical(fromX)
      const toLogical = timeScale.coordinateToLogical(toX)
      if (fromLogical === null || toLogical === null || toLogical <= fromLogical) {
        return
      }

      const visibleSpan = toLogical - fromLogical
      const barSpacing = chartWidth / visibleSpan
      const baseIndex = dataRef.current?.rows.length ? dataRef.current.rows.length - 1 : null
      if (baseIndex === null) {
        return
      }

      chart.applyOptions({
        timeScale: {
          barSpacing,
          rightOffset: toLogical - baseIndex,
        },
      })
    }

    const shouldStartSelection = (event: PointerEvent) =>
      event.button === 0 && (event.shiftKey || zoomSelectModeRef.current)

    const localX = (event: PointerEvent) => {
      const rect = wrapper.getBoundingClientRect()
      return event.clientX - rect.left
    }

    const onPointerDown = (event: PointerEvent) => {
      if (!shouldStartSelection(event)) {
        return
      }

      event.preventDefault()
      event.stopPropagation()
      const startX = localX(event)
      selectingRef.current = { startX, pointerId: event.pointerId }
      wrapper.setPointerCapture(event.pointerId)
      updateSelection(startX, startX)
    }

    const onPointerMove = (event: PointerEvent) => {
      const selecting = selectingRef.current
      if (!selecting || selecting.pointerId !== event.pointerId) {
        return
      }

      event.preventDefault()
      updateSelection(selecting.startX, localX(event))
    }

    const onPointerUp = (event: PointerEvent) => {
      const selecting = selectingRef.current
      if (!selecting || selecting.pointerId !== event.pointerId) {
        return
      }

      event.preventDefault()
      finishSelection(selecting.startX, localX(event))
      selectingRef.current = null
      if (wrapper.hasPointerCapture(event.pointerId)) {
        wrapper.releasePointerCapture(event.pointerId)
      }
    }

    wrapper.addEventListener('pointerdown', onPointerDown, true)
    wrapper.addEventListener('pointermove', onPointerMove, true)
    wrapper.addEventListener('pointerup', onPointerUp, true)
    wrapper.addEventListener('pointercancel', onPointerUp, true)

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) {
        return
      }
      const { width, height } = entry.contentRect
      chart.applyOptions({ width, height })
      updateBoundaryPositions()
    })
    observer.observe(container)

    updateBoundaryPositions()

    return () => {
      wrapper.removeEventListener('pointerdown', onPointerDown, true)
      wrapper.removeEventListener('pointermove', onPointerMove, true)
      wrapper.removeEventListener('pointerup', onPointerUp, true)
      wrapper.removeEventListener('pointercancel', onPointerUp, true)
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      timeScale.unsubscribeVisibleTimeRangeChange(onVisibleTimeRangeChange)
      observer.disconnect()
      markersRef.current?.detach()
      markersRef.current = null
      chart.remove()
      chartRef.current = null
      setChartInstance(null)
      seriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [
    appearance.chart_down_color,
    appearance.chart_grid_visible,
    appearance.chart_up_color,
    appearance.indicator_contrast,
    appearance.time_display_format,
    platformSettings.platform_behavior.timezone,
    chartTheme.background,
    chartTheme.border,
    chartTheme.grid,
    chartTheme.labelBackground,
    chartTheme.mutedText,
    chartTheme.paneSeparator,
    chartTheme.paneSeparatorHover,
    chartTheme.text,
    chartTheme.tooltipBorder,
    resolvedThemeMode,
    updateBoundaryPositions,
  ])

  useEffect(() => {
    const series = seriesRef.current
    const volumeSeries = volumeSeriesRef.current
    const chart = chartRef.current
    const markers = markersRef.current
    if (!series || !volumeSeries || !chart || !markers) {
      return
    }

    if (!data || data.rows.length === 0) {
      series.setData([])
      volumeSeries.setData([])
      markers.setMarkers([])
      return
    }

    series.setData(toCandlestickData(data))
    volumeSeries.setData(toVolumeData(data, appearance.chart_up_color, appearance.chart_down_color))
    markers.setMarkers(toAnnotationMarkers(data, orders, trades, annotationMarkers ?? []))
    if (!focusRange) {
      chart.timeScale().fitContent()
    }
    updateBoundaryPositions()
  }, [
    appearance.chart_down_color,
    appearance.chart_up_color,
    annotationMarkers,
    data,
    focusRange,
    orders,
    trades,
    updateBoundaryPositions,
  ])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !focusRange) {
      return
    }

    chart.timeScale().setVisibleRange(focusRange)
  }, [focusRange])

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        minHeight: 420,
      }}
    >
      <Box
        ref={wrapperRef}
        sx={{
          position: 'relative',
          flex: 1,
          minHeight: 360,
          cursor: zoomSelectMode ? 'crosshair' : 'default',
        }}
      >
        <Box
          ref={chartContainerRef}
          sx={{
            width: '100%',
            height: '100%',
          }}
        />

        {boundaryPositions.map((left, index) => (
          <Box
            key={`${left}-${index}`}
            sx={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left,
              borderLeft: `1px dashed ${chartTheme.dayBoundary}`,
              opacity: 0.9,
              pointerEvents: 'none',
              zIndex: 1,
            }}
          />
        ))}

        <Box
          ref={selectionRef}
          sx={{
            display: 'none',
            position: 'absolute',
            top: 0,
            bottom: 0,
            pointerEvents: 'none',
            bgcolor: chartTheme.selectionBackground,
            border: `1px solid ${chartTheme.selectionBorder}`,
            zIndex: 1,
          }}
        />

        <Box
          ref={tooltipRef}
          sx={{
            display: 'none',
            position: 'absolute',
            zIndex: 2,
            pointerEvents: 'none',
            px: 1.25,
            py: 1,
            fontSize: 12,
            lineHeight: 1.5,
            color: chartTheme.tooltipText,
            bgcolor: chartTheme.tooltipBackground,
            border: `1px solid ${chartTheme.tooltipBorder}`,
            borderRadius: 1,
            boxShadow: '0 4px 16px rgba(0,0,0,0.45)',
            maxWidth: 280,
          }}
        />

        <Stack
          direction="row"
          spacing={0.5}
          sx={{
            position: 'absolute',
            top: 8,
            left: 8,
            zIndex: 2,
            alignItems: 'center',
            bgcolor: chartTheme.controlBackground,
            border: `1px solid ${chartTheme.controlBorder}`,
            borderRadius: 1,
            p: 0.5,
          }}
        >
          <Tooltip title={zoomSelectMode ? 'Drag to select a range' : 'Enable drag-to-zoom mode'}>
            <ToggleButton
              value="zoom"
              selected={zoomSelectMode}
              size="small"
              onChange={() => setZoomSelectMode((current) => !current)}
              aria-label="Toggle range zoom"
              sx={{ px: 1 }}
            >
              <ZoomInMapIcon fontSize="small" />
            </ToggleButton>
          </Tooltip>
          <Tooltip title="Reset zoom">
            <IconButton size="small" onClick={resetZoom} aria-label="Reset zoom">
              <RestartAltIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ px: 0.5, display: { xs: 'none', sm: 'block' } }}
          >
            {zoomSelectMode ? 'Drag to zoom' : 'Shift+drag to zoom'}
          </Typography>
        </Stack>
      </Box>

      {showViewportWindow && !focusRange && (
        <ChartViewportWindow
          key={data ? `${data.symbol}-${data.start_date}-${data.stop_date}-${data.rows.length}` : 'empty'}
          chart={chartInstance}
          dataRange={dataRange}
          timezone={platformSettings.platform_behavior.timezone}
          timeDisplayFormat={appearance.time_display_format}
        />
      )}
    </Box>
  )
}
