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
  type UTCTimestamp,
} from 'lightweight-charts'
import { useCallback, useEffect, useRef, useState } from 'react'

import { useSettings } from '../settings/useSettings'
import type { OrderRecord } from '../types/dayBacktest'
import type { MarketDataResponse } from '../types/marketData'

interface CandlestickChartProps {
  data: MarketDataResponse | null
  orders?: OrderRecord[]
}

const BUY_MARKER_COLOR = '#58a6ff'
const SELL_MARKER_COLOR = '#f0883e'
const MIN_SELECTION_PX = 8
const VOLUME_PANE_STRETCH = 0.28

function toChartTime(timestamp: string, resolution: string): Time {
  if (resolution === '1d') {
    return timestamp.slice(0, 10) as Time
  }
  return Math.floor(Date.parse(timestamp) / 1000) as UTCTimestamp
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

function toOrderMarkers(data: MarketDataResponse, orders: OrderRecord[]): SeriesMarker<Time>[] {
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

  return markers.sort((left, right) => Number(left.time) - Number(right.time))
}

function formatBarTime(
  timestamp: string,
  resolution: string,
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  if (resolution === '1d') {
    return timestamp.slice(0, 10)
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

function buildTooltipHtml(
  bar: { open: number; high: number; low: number; close: number; volume: number; timestamp: string },
  resolution: string,
  ordersAtBar: OrderRecord[],
  timezone: string,
  timeDisplayFormat: '12h' | '24h',
): string {
  const lines = [
    `<div style="font-weight:600;margin-bottom:4px">${formatBarTime(bar.timestamp, resolution, timezone, timeDisplayFormat)}</div>`,
    `<div>O ${bar.open.toFixed(2)} &nbsp; H ${bar.high.toFixed(2)} &nbsp; L ${bar.low.toFixed(2)} &nbsp; C ${bar.close.toFixed(2)}</div>`,
    `<div style="margin-top:4px">Vol ${formatVolume(bar.volume)}</div>`,
  ]

  if (ordersAtBar.length > 0) {
    lines.push('<div style="margin-top:6px;border-top:1px solid #30363d;padding-top:6px">')
    lines.push(ordersAtBar.map(formatOrderLine).join(''))
    lines.push('</div>')
  }

  return lines.join('')
}

export function CandlestickChart({ data, orders = [] }: CandlestickChartProps) {
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
  const zoomSelectModeRef = useRef(false)
  const selectingRef = useRef<{ startX: number; pointerId: number } | null>(null)

  const [zoomSelectMode, setZoomSelectMode] = useState(false)

  useEffect(() => {
    dataRef.current = data
    ordersRef.current = orders
  }, [data, orders])

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
  }, [])

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
          color: theme.palette.background.paper,
        },
        textColor:
          appearance.indicator_contrast === 'high' ? theme.palette.text.primary : '#c9d1d9',
        panes: {
          separatorColor: appearance.indicator_contrast === 'high' ? '#556170' : '#30363d',
          separatorHoverColor: appearance.indicator_contrast === 'high' ? '#7d8898' : '#484f58',
          enableResize: true,
        },
      },
      grid: {
        vertLines: { color: appearance.chart_grid_visible ? '#30363d' : 'transparent' },
        horzLines: { color: appearance.chart_grid_visible ? '#30363d' : 'transparent' },
      },
      rightPriceScale: {
        borderColor: '#30363d',
      },
      timeScale: {
        borderColor: '#30363d',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { labelBackgroundColor: '#30363d' },
        horzLine: { labelBackgroundColor: '#30363d' },
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
      tooltip.innerHTML = buildTooltipHtml(
        row,
        chartData.resolution,
        ordersAtBar,
        platformSettings.platform_behavior.timezone,
        appearance.time_display_format,
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
      const fromLogical = timeScale.coordinateToLogical(Math.min(startX, endX))
      const toLogical = timeScale.coordinateToLogical(Math.max(startX, endX))
      if (fromLogical === null || toLogical === null) {
        return
      }

      timeScale.setVisibleLogicalRange({ from: fromLogical, to: toLogical })
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
    })
    observer.observe(container)

    return () => {
      wrapper.removeEventListener('pointerdown', onPointerDown, true)
      wrapper.removeEventListener('pointermove', onPointerMove, true)
      wrapper.removeEventListener('pointerup', onPointerUp, true)
      wrapper.removeEventListener('pointercancel', onPointerUp, true)
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      observer.disconnect()
      markersRef.current?.detach()
      markersRef.current = null
      chart.remove()
      chartRef.current = null
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
    theme.palette.background.paper,
    theme.palette.text.primary,
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
    markers.setMarkers(toOrderMarkers(data, orders))
    chart.timeScale().fitContent()
  }, [appearance.chart_down_color, appearance.chart_up_color, data, orders])

  return (
    <Box
      ref={wrapperRef}
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 420,
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

      <Box
        ref={selectionRef}
        sx={{
          display: 'none',
          position: 'absolute',
          top: 0,
          bottom: 0,
          pointerEvents: 'none',
          bgcolor: 'rgba(88, 166, 255, 0.12)',
          border: '1px solid rgba(88, 166, 255, 0.55)',
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
          color: '#c9d1d9',
          bgcolor: 'rgba(22, 27, 34, 0.96)',
          border: '1px solid #30363d',
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
          bgcolor: 'rgba(22, 27, 34, 0.88)',
          border: '1px solid #30363d',
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
        <Typography variant="caption" color="text.secondary" sx={{ px: 0.5, display: { xs: 'none', sm: 'block' } }}>
          {zoomSelectMode ? 'Drag to zoom' : 'Shift+drag to zoom'}
        </Typography>
      </Stack>
    </Box>
  )
}
