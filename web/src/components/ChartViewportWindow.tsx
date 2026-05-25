import { Box, Typography } from '@mui/material'
import type { IChartApi, Time } from 'lightweight-charts'
import { useCallback, useEffect, useRef, useState } from 'react'

import { chartTimeToMs, formatChartTime } from '../utils/chartTime'
import type { TimeDisplayFormat } from '../types/settings'

interface ChartViewportWindowProps {
  chart: IChartApi | null
  dataRange: { from: Time; to: Time } | null
  timezone: string
  timeDisplayFormat: TimeDisplayFormat
}

type DragMode = 'pan' | 'resize-left' | 'resize-right'

const HANDLE_WIDTH = 8
const MIN_WINDOW_MS = 60_000

function formatRangeLabel(
  from: Time,
  to: Time,
  timezone: string,
  timeDisplayFormat: TimeDisplayFormat,
): string {
  return `${formatChartTime(from, timezone, timeDisplayFormat)} → ${formatChartTime(to, timezone, timeDisplayFormat)}`
}

export function ChartViewportWindow({ chart, dataRange, timezone, timeDisplayFormat }: ChartViewportWindowProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [visibleRange, setVisibleRange] = useState<{ from: Time; to: Time } | null>(null)
  const dragRef = useRef<{
    mode: DragMode
    pointerId: number
    startX: number
    startFromMs: number
    startToMs: number
  } | null>(null)

  const syncFromChart = useCallback(() => {
    if (!chart) {
      return
    }
    const range = chart.timeScale().getVisibleRange()
    if (range) {
      setVisibleRange(range)
    }
  }, [chart])

  useEffect(() => {
    if (!chart) {
      return undefined
    }

    syncFromChart()
    const timeScale = chart.timeScale()
    timeScale.subscribeVisibleTimeRangeChange(syncFromChart)

    return () => {
      timeScale.unsubscribeVisibleTimeRangeChange(syncFromChart)
    }
  }, [chart, syncFromChart])

  useEffect(() => {
    if (visibleRange || !dataRange || !chart) {
      return
    }

    let cancelled = false
    let attempts = 0

    const initializeRange = () => {
      if (cancelled || attempts >= 8) {
        return
      }
      attempts += 1
      try {
        chart.timeScale().fitContent()
        syncFromChart()
      } catch {
        window.requestAnimationFrame(initializeRange)
      }
    }

    window.requestAnimationFrame(initializeRange)
    return () => {
      cancelled = true
    }
  }, [chart, dataRange, visibleRange, syncFromChart])

  if (!dataRange || !visibleRange) {
    return null
  }

  const dataFromMs = chartTimeToMs(dataRange.from)
  const dataToMs = chartTimeToMs(dataRange.to)
  const dataSpanMs = Math.max(dataToMs - dataFromMs, MIN_WINDOW_MS)

  const visibleFromMs = chartTimeToMs(visibleRange.from)
  const visibleToMs = chartTimeToMs(visibleRange.to)

  const leftPct = ((visibleFromMs - dataFromMs) / dataSpanMs) * 100
  const widthPct = ((visibleToMs - visibleFromMs) / dataSpanMs) * 100

  const msToTime = (ms: number): Time => {
    if (typeof dataRange.from === 'number') {
      return Math.floor(ms / 1000) as Time
    }
    return new Date(ms).toISOString().slice(0, 10) as Time
  }

  const applyRange = (fromMs: number, toMs: number) => {
    if (!chart) {
      return
    }
    const minSpan = Math.min(MIN_WINDOW_MS, dataSpanMs)
    let nextFrom = fromMs
    let nextTo = toMs

    if (nextTo - nextFrom < minSpan) {
      nextTo = nextFrom + minSpan
    }
    if (nextFrom < dataFromMs) {
      nextFrom = dataFromMs
      nextTo = Math.min(dataFromMs + minSpan, dataToMs)
    }
    if (nextTo > dataToMs) {
      nextTo = dataToMs
      nextFrom = Math.max(dataToMs - minSpan, dataFromMs)
    }

    const range = { from: msToTime(nextFrom), to: msToTime(nextTo) }
    chart.timeScale().setVisibleRange(range)
    setVisibleRange(range)
  }

  const localX = (event: PointerEvent) => {
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) {
      return 0
    }
    return Math.max(0, Math.min(event.clientX - rect.left, rect.width))
  }

  const xToMs = (x: number) => {
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) {
      return dataFromMs
    }
    const ratio = x / rect.width
    return dataFromMs + ratio * dataSpanMs
  }

  const onPointerDown = (mode: DragMode) => (event: React.PointerEvent) => {
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = {
      mode,
      pointerId: event.pointerId,
      startX: localX(event.nativeEvent),
      startFromMs: visibleFromMs,
      startToMs: visibleToMs,
    }
    trackRef.current?.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) {
      return
    }

    event.preventDefault()
    const deltaX = localX(event.nativeEvent) - drag.startX
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) {
      return
    }
    const deltaMs = (deltaX / rect.width) * dataSpanMs

    if (drag.mode === 'pan') {
      applyRange(drag.startFromMs + deltaMs, drag.startToMs + deltaMs)
      return
    }

    if (drag.mode === 'resize-left') {
      applyRange(drag.startFromMs + deltaMs, drag.startToMs)
      return
    }

    applyRange(drag.startFromMs, drag.startToMs + deltaMs)
  }

  const onPointerUp = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) {
      return
    }
    dragRef.current = null
    if (trackRef.current?.hasPointerCapture(event.pointerId)) {
      trackRef.current.releasePointerCapture(event.pointerId)
    }
  }

  const onTrackClick = (event: React.PointerEvent) => {
    if (dragRef.current || event.button !== 0) {
      return
    }
    const clickMs = xToMs(localX(event.nativeEvent))
    const span = visibleToMs - visibleFromMs
    applyRange(clickMs - span / 2, clickMs + span / 2)
  }

  return (
    <Box sx={{ px: 1, pb: 1, pt: 0.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, px: 0.5 }}>
        Viewport · {formatRangeLabel(visibleRange.from, visibleRange.to, timezone, timeDisplayFormat)}
      </Typography>
      <Box
        ref={trackRef}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerDown={onTrackClick}
        sx={{
          position: 'relative',
          height: 28,
          bgcolor: 'rgba(48, 54, 61, 0.5)',
          border: '1px solid #30363d',
          borderRadius: 1,
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <Box
          onPointerDown={onPointerDown('pan')}
          sx={{
            position: 'absolute',
            top: 2,
            bottom: 2,
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            minWidth: HANDLE_WIDTH * 2,
            bgcolor: 'rgba(88, 166, 255, 0.22)',
            border: '1px solid rgba(88, 166, 255, 0.65)',
            borderRadius: 0.5,
            cursor: 'grab',
            '&:active': { cursor: 'grabbing' },
          }}
        >
          <Box
            onPointerDown={onPointerDown('resize-left')}
            sx={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: HANDLE_WIDTH,
              cursor: 'ew-resize',
              borderTopLeftRadius: 4,
              borderBottomLeftRadius: 4,
              bgcolor: 'rgba(88, 166, 255, 0.35)',
            }}
          />
          <Box
            onPointerDown={onPointerDown('resize-right')}
            sx={{
              position: 'absolute',
              right: 0,
              top: 0,
              bottom: 0,
              width: HANDLE_WIDTH,
              cursor: 'ew-resize',
              borderTopRightRadius: 4,
              borderBottomRightRadius: 4,
              bgcolor: 'rgba(88, 166, 255, 0.35)',
            }}
          />
        </Box>
      </Box>
    </Box>
  )
}
