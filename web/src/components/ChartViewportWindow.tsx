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
  const panHandleRef = useRef<HTMLDivElement>(null)
  const leftHandleRef = useRef<HTMLDivElement>(null)
  const rightHandleRef = useRef<HTMLDivElement>(null)
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

    const timeScale = chart.timeScale()
    const onVisibleTimeRangeChange = () => syncFromChart()
    timeScale.subscribeVisibleTimeRangeChange(onVisibleTimeRangeChange)

    const raf = window.requestAnimationFrame(onVisibleTimeRangeChange)
    return () => {
      window.cancelAnimationFrame(raf)
      timeScale.unsubscribeVisibleTimeRangeChange(onVisibleTimeRangeChange)
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

    const raf = window.requestAnimationFrame(initializeRange)
    return () => {
      cancelled = true
      window.cancelAnimationFrame(raf)
    }
  }, [chart, dataRange, visibleRange, syncFromChart])

  const dataFromMs = dataRange ? chartTimeToMs(dataRange.from) : 0
  const dataToMs = dataRange ? chartTimeToMs(dataRange.to) : 0
  const dataSpanMs = Math.max(dataToMs - dataFromMs, MIN_WINDOW_MS)

  const visibleFromMs = visibleRange ? chartTimeToMs(visibleRange.from) : dataFromMs
  const visibleToMs = visibleRange ? chartTimeToMs(visibleRange.to) : dataToMs

  const localX = useCallback((event: PointerEvent) => {
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) {
      return 0
    }
    return Math.max(0, Math.min(event.clientX - rect.left, rect.width))
  }, [])

  const xToMs = useCallback(
    (x: number) => {
      const rect = trackRef.current?.getBoundingClientRect()
      if (!rect || rect.width === 0) {
        return dataFromMs
      }
      const ratio = x / rect.width
      return dataFromMs + ratio * dataSpanMs
    },
    [dataFromMs, dataSpanMs],
  )

  const applyRange = useCallback(
    (fromMs: number, toMs: number) => {
      if (!chart || !dataRange) {
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

      const range: { from: Time; to: Time } = {
        from: typeof dataRange.from === 'number' ? (Math.floor(nextFrom / 1000) as Time) : (new Date(nextFrom).toISOString().slice(0, 10) as Time),
        to: typeof dataRange.from === 'number' ? (Math.floor(nextTo / 1000) as Time) : (new Date(nextTo).toISOString().slice(0, 10) as Time),
      }
      chart.timeScale().setVisibleRange(range)
      setVisibleRange(range)
    },
    [chart, dataFromMs, dataRange, dataSpanMs, dataToMs],
  )

  useEffect(() => {
    const track = trackRef.current
    const panHandle = panHandleRef.current
    const leftHandle = leftHandleRef.current
    const rightHandle = rightHandleRef.current
    if (!track || !panHandle || !leftHandle || !rightHandle) {
      return undefined
    }

    const handlePointerDown = (mode: DragMode) => (event: PointerEvent) => {
      event.preventDefault()
      event.stopPropagation()
      dragRef.current = {
        mode,
        pointerId: event.pointerId,
        startX: localX(event),
        startFromMs: visibleFromMs,
        startToMs: visibleToMs,
      }
      track.setPointerCapture(event.pointerId)
    }

    const handlePointerMove = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) {
        return
      }

      event.preventDefault()
      const rect = track.getBoundingClientRect()
      if (!rect) {
        return
      }
      const deltaX = localX(event) - drag.startX
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

    const handlePointerUp = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) {
        return
      }

      dragRef.current = null
      if (track.hasPointerCapture(event.pointerId)) {
        track.releasePointerCapture(event.pointerId)
      }
    }

    const handleTrackClick = (event: PointerEvent) => {
      if (dragRef.current || event.button !== 0) {
        return
      }
      const clickMs = xToMs(localX(event))
      const span = visibleToMs - visibleFromMs
      applyRange(clickMs - span / 2, clickMs + span / 2)
    }

    const handlePanPointerDown = handlePointerDown('pan')
    const handleLeftPointerDown = handlePointerDown('resize-left')
    const handleRightPointerDown = handlePointerDown('resize-right')

    track.addEventListener('pointermove', handlePointerMove)
    track.addEventListener('pointerup', handlePointerUp)
    track.addEventListener('pointercancel', handlePointerUp)
    track.addEventListener('pointerdown', handleTrackClick)
    panHandle.addEventListener('pointerdown', handlePanPointerDown)
    leftHandle.addEventListener('pointerdown', handleLeftPointerDown)
    rightHandle.addEventListener('pointerdown', handleRightPointerDown)

    return () => {
      track.removeEventListener('pointermove', handlePointerMove)
      track.removeEventListener('pointerup', handlePointerUp)
      track.removeEventListener('pointercancel', handlePointerUp)
      track.removeEventListener('pointerdown', handleTrackClick)
      panHandle.removeEventListener('pointerdown', handlePanPointerDown)
      leftHandle.removeEventListener('pointerdown', handleLeftPointerDown)
      rightHandle.removeEventListener('pointerdown', handleRightPointerDown)
    }
  }, [applyRange, dataSpanMs, localX, visibleFromMs, visibleToMs, xToMs])

  if (!dataRange || !visibleRange) {
    return null
  }

  const leftPct = ((visibleFromMs - dataFromMs) / dataSpanMs) * 100
  const widthPct = ((visibleToMs - visibleFromMs) / dataSpanMs) * 100

  return (
    <Box sx={{ px: 1, pb: 1, pt: 0.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, px: 0.5 }}>
        Viewport · {formatRangeLabel(visibleRange.from, visibleRange.to, timezone, timeDisplayFormat)}
      </Typography>
      <Box
        ref={trackRef}
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
          ref={panHandleRef}
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
            ref={leftHandleRef}
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
            ref={rightHandleRef}
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
