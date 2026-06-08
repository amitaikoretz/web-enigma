import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { fetchLatestMarketOverview, launchMarketOverview } from '../api/marketOverview'
import { useSettings } from '../settings/useSettings'
import type {
  MarketOverviewIndicator,
  MarketOverviewMethodology,
  MarketOverviewSnapshot,
} from '../types/marketOverview'

type Tone = NonNullable<MarketOverviewIndicator['tone']>

const DEFAULT_METHODOLOGY: MarketOverviewMethodology = {
  summary:
    'The overview blends cross-asset indicators, breadth, volatility, credit, rates, macro, and earnings signals into a weighted regime read.',
  inputs: [
    'Major equity indices and relative breadth',
    'Volatility, credit, rates, and FX context',
    'Pillar scores for trend, breadth, and macro regime',
    'Recent developments ranked by market impact',
  ],
  scoring: [
    'Each pillar contributes a normalized score that maps into the regime candidate set.',
    'Probability weights reflect agreement between price action, breadth, and cross-asset signals.',
    'Confidence rises when the top regime leads by a wide margin and freshness is good.',
    'Fragility rises when breadth narrows, yields rise, or the market becomes more concentrated.',
  ],
  freshness: 'Fresh inputs increase confidence. Stale data is surfaced explicitly and lowers trust in the current read.',
  caveats: [
    'The label is probabilistic, not deterministic.',
    'A strong index can still be fragile when participation is narrow.',
  ],
}

const OVERVIEW_RELOAD_POLL_INTERVAL_MS = 250

function formatPercent(value: number): string {
  return `${Math.round(value)}%`
}

function formatProbability(value: number): string {
  return `${Math.round(value * 100)}%`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function formatRelativeMinutes(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const diffMinutes = Math.round((Date.now() - date.getTime()) / 60_000)
  if (diffMinutes < 1) {
    return 'just now'
  }
  if (diffMinutes === 1) {
    return '1 minute ago'
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} minutes ago`
  }
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours === 1) {
    return '1 hour ago'
  }
  if (diffHours < 24) {
    return `${diffHours} hours ago`
  }
  const diffDays = Math.round(diffHours / 24)
  return `${diffDays} days ago`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  if (typeof value === 'string') {
    return value
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item)).join(', ')
  }
  if (isRecord(value)) {
    return JSON.stringify(value)
  }
  return String(value)
}

function titleize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function toneColor(tone: Tone): 'success' | 'error' | 'warning' | 'info' | 'default' {
  switch (tone) {
    case 'positive':
      return 'success'
    case 'negative':
      return 'error'
    case 'warning':
      return 'warning'
    case 'info':
      return 'info'
    default:
      return 'default'
  }
}

function tonePaletteKey(tone: Tone): 'primary' | 'success' | 'error' | 'warning' | 'info' {
  switch (tone) {
    case 'positive':
      return 'success'
    case 'negative':
      return 'error'
    case 'warning':
      return 'warning'
    case 'info':
      return 'info'
    default:
      return 'primary'
  }
}

function resolveTone(tone?: MarketOverviewIndicator['tone']): Tone {
  return tone ?? 'neutral'
}

function resolveMethodology(snapshot: MarketOverviewSnapshot | null): MarketOverviewMethodology {
  const methodology = snapshot?.methodology
  if (!methodology) {
    return DEFAULT_METHODOLOGY
  }

  return {
    summary: methodology.summary || DEFAULT_METHODOLOGY.summary,
    inputs: methodology.inputs.length > 0 ? methodology.inputs : DEFAULT_METHODOLOGY.inputs,
    scoring: methodology.scoring.length > 0 ? methodology.scoring : DEFAULT_METHODOLOGY.scoring,
    freshness: methodology.freshness ?? DEFAULT_METHODOLOGY.freshness,
    caveats: methodology.caveats.length > 0 ? methodology.caveats : DEFAULT_METHODOLOGY.caveats,
  }
}

function resolveIndicators(snapshot: MarketOverviewSnapshot | null): MarketOverviewIndicator[] {
  return snapshot?.market_indicators ?? []
}

function resolveWatchNext(
  snapshot: MarketOverviewSnapshot | null,
  indicators: MarketOverviewIndicator[],
  methodology: MarketOverviewMethodology,
): string[] {
  if (snapshot?.watch_next && snapshot.watch_next.length > 0) {
    return snapshot.watch_next
  }

  const warningSignals = indicators
    .filter((indicator) => {
      const tone = resolveTone(indicator.tone)
      return tone === 'warning' || tone === 'negative'
    })
    .slice(0, 3)
    .map((indicator) => `${indicator.label}: ${indicator.note ?? indicator.change ?? indicator.value}`)

  if (warningSignals.length > 0) {
    return warningSignals
  }

  return methodology.caveats.length > 0
    ? methodology.caveats
    : ['No watch-next signals are available yet.']
}

function scoreTone(value: unknown): Tone {
  if (typeof value !== 'number') {
    return 'neutral'
  }
  if (value > 0) {
    return 'positive'
  }
  if (value < 0) {
    return 'negative'
  }
  return 'neutral'
}

function scoreLabel(value: unknown): string {
  if (typeof value !== 'number') {
    return formatValue(value)
  }
  const signed = value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1)
  return signed
}

function indicatorBarValue(value: unknown): number | null {
  if (typeof value !== 'number') {
    return null
  }
  const scaled = ((value + 2) / 4) * 100
  return Math.max(0, Math.min(100, scaled))
}

function isStale(snapshot: MarketOverviewSnapshot | null): boolean {
  if (!snapshot) {
    return false
  }
  const updatedAt = new Date(snapshot.updated_at)
  return !Number.isNaN(updatedAt.getTime()) && Date.now() - updatedAt.getTime() > 60 * 60 * 1000
}

function isTerminalMarketOverviewStatus(status: MarketOverviewSnapshot['status']): boolean {
  return status === 'completed' || status === 'failed'
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function getIndicatorExplanationContent(indicator: MarketOverviewIndicator) {
  const explanation = indicator.explanation
  const summary = typeof explanation?.summary === 'string' ? explanation.summary.trim() : ''
  const inputCandidates = explanation?.inputs
  const inputs = Array.isArray(inputCandidates)
    ? inputCandidates.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
  const calculationCandidates = explanation?.calculation_steps
  const calculationSteps = Array.isArray(calculationCandidates)
    ? calculationCandidates.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
  const interpretation = typeof explanation?.interpretation === 'string' ? explanation.interpretation.trim() : ''
  const freshness = typeof explanation?.freshness === 'string' ? explanation.freshness.trim() : ''
  const caveatCandidates = explanation?.caveats
  const caveats = Array.isArray(caveatCandidates)
    ? caveatCandidates.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
  return { summary, inputs, calculationSteps, interpretation, freshness, caveats }
}

function IndicatorExplanationDialog({
  indicator,
  open,
  onClose,
}: {
  indicator: MarketOverviewIndicator | null
  open: boolean
  onClose: () => void
}) {
  const content = indicator ? getIndicatorExplanationContent(indicator) : null
  const hasExplanation = Boolean(
    content &&
      (content.summary ||
        content.inputs.length > 0 ||
        content.calculationSteps.length > 0 ||
        content.interpretation ||
        content.freshness ||
        content.caveats.length > 0),
  )

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      slotProps={{ paper: { sx: { overflow: 'hidden' } } }}
    >
      <DialogTitle
        sx={(theme) => ({
          pr: 6,
          pb: 1.25,
          background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.14)}, ${alpha(
            theme.palette.background.paper,
            1,
          )})`,
        })}
      >
        <Stack spacing={0.5}>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.16em' }}>
            Indicator explanation
          </Typography>
          <Typography variant="h6" component="div">
            {indicator?.label ?? 'Explanation'}
          </Typography>
          {indicator ? (
            <Typography variant="body2" color="text.secondary">
              {indicator.category ? `${titleize(indicator.category)} · ` : ''}
              {indicator.value}
              {indicator.change ? ` · ${indicator.change}` : ''}
            </Typography>
          ) : null}
        </Stack>
        <IconButton
          aria-label="Close explanation"
          onClick={onClose}
          sx={{ position: 'absolute', right: 16, top: 16 }}
        >
          <CloseRoundedIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 2.5, pb: 3 }}>
        {indicator && hasExplanation ? (
          <Stack spacing={2}>
            <Typography variant="body1" sx={{ lineHeight: 1.7 }}>
              {content?.summary}
            </Typography>

            {content?.inputs.length ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                  Inputs
                </Typography>
                <Stack component="ul" spacing={0.75} sx={{ m: 0, pl: 2.5 }}>
                  {content.inputs.map((item) => (
                    <Typography key={item} component="li" variant="body2" sx={{ lineHeight: 1.6 }}>
                      {item}
                    </Typography>
                  ))}
                </Stack>
              </Stack>
            ) : null}

            {content?.calculationSteps.length ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                  Computation
                </Typography>
                <Stack spacing={1}>
                  {content.calculationSteps.map((item, index) => (
                    <Stack key={item} direction="row" spacing={1.25} sx={{ alignItems: 'flex-start' }}>
                      <Chip label={String(index + 1)} size="small" color="primary" variant="outlined" />
                      <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                        {item}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </Stack>
            ) : null}

            {content?.interpretation ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                  Interpretation
                </Typography>
                <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                  {content.interpretation}
                </Typography>
              </Stack>
            ) : null}

            {content?.freshness ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                  Freshness
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                  {content.freshness}
                </Typography>
              </Stack>
            ) : null}

            {content?.caveats.length ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                  Caveats
                </Typography>
                <Stack component="ul" spacing={0.75} sx={{ m: 0, pl: 2.5 }}>
                  {content.caveats.map((item) => (
                    <Typography key={item} component="li" variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                      {item}
                    </Typography>
                  ))}
                </Stack>
              </Stack>
            ) : null}
          </Stack>
        ) : (
          <Typography variant="body1" sx={{ lineHeight: 1.7 }}>
            {indicator?.note ?? 'No detailed computation notes were supplied for this indicator yet.'}
          </Typography>
        )}
      </DialogContent>
    </Dialog>
  )
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, md: 2.5 },
        borderRadius: 4,
      }}
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.14em' }}>
            {title}
          </Typography>
          {subtitle ? (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          ) : null}
        </Stack>
        {children}
      </Stack>
    </Paper>
  )
}

type OverviewMetricKey = 'confidence' | 'fragility' | 'contradiction' | 'freshness'

interface OverviewMetricDefinition {
  key: OverviewMetricKey
  label: string
  value: string
  helper?: string
}

function renderMethodologySection(methodology: MarketOverviewMethodology) {
  return (
    <Stack spacing={2}>
      <Typography variant="body1" sx={{ lineHeight: 1.7 }}>
        {methodology.summary}
      </Typography>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Inputs
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          {methodology.inputs.map((item) => (
            <Chip key={item} label={item} size="small" variant="outlined" />
          ))}
        </Stack>
      </Box>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Scoring
        </Typography>
        <Stack spacing={1}>
          {methodology.scoring.map((item, index) => (
            <Stack key={item} direction="row" spacing={1.25} sx={{ alignItems: 'flex-start' }}>
              <Chip label={String(index + 1)} size="small" color="primary" variant="outlined" />
              <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                {item}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Box>

      <Divider />

      <Stack spacing={1}>
        <Typography variant="subtitle2">Freshness</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
          {methodology.freshness}
        </Typography>
      </Stack>

      {methodology.caveats.length > 0 ? (
        <>
          <Divider />
          <Stack spacing={1}>
            <Typography variant="subtitle2">Caveats</Typography>
            <Stack component="ul" spacing={1} sx={{ m: 0, pl: 3 }}>
              {methodology.caveats.map((item) => (
                <Typography key={item} component="li" variant="body2" color="text.secondary">
                  {item}
                </Typography>
              ))}
            </Stack>
          </Stack>
        </>
      ) : null}
    </Stack>
  )
}

function getMetricModalIntro(
  metric: OverviewMetricKey,
  snapshot: MarketOverviewSnapshot | null,
  nextRefreshAt: Date | null,
): {
  title: string
  summary: string
  bullets: string[]
  footer?: string
} {
  const confidence = formatPercent(snapshot?.confidence ?? 0)
  const fragility = formatPercent(snapshot?.fragility ?? 0)
  const contradiction = formatPercent(snapshot?.contradiction_score ?? 0)
  const freshness = snapshot?.updated_at ? formatRelativeMinutes(snapshot.updated_at) : '—'

  switch (metric) {
    case 'confidence':
      return {
        title: 'Confidence',
        summary:
          'Confidence is the probability gap and signal agreement score that comes out of the weighted regime read described below.',
        bullets: [
          `Current confidence: ${confidence}.`,
          'Higher confidence usually means the leading regime is clearly ahead of the alternatives.',
          'Low confidence means the weighted inputs disagree more and the read should be treated as tentative.',
        ],
        footer: snapshot?.top_regime ? `Current regime: ${snapshot.top_regime}.` : undefined,
      }
    case 'fragility':
      return {
        title: 'Fragility',
        summary:
          'Fragility measures how exposed the current regime is to a break if breadth, rates, credit, or concentration change.',
        bullets: [
          `Current fragility: ${fragility}.`,
          'This rises when the same methodology sees more concentration, more yield pressure, or weaker participation.',
          'A healthy-looking regime can still be fragile if the underlying signals are not broad-based.',
        ],
        footer: snapshot?.summary_text ? 'The regime can still look healthy even when fragility is elevated.' : undefined,
      }
    case 'contradiction':
      return {
        title: 'Contradiction',
        summary:
          'Contradiction is the disagreement score created when the cross-asset and breadth signals do not line up cleanly.',
        bullets: [
          `Current contradiction score: ${contradiction}.`,
          'The same weighted regime read becomes less settled when the inputs point in different directions.',
          'This is a useful prompt to inspect the underlying inputs and caveats listed below.',
        ],
        footer: snapshot?.market_indicators?.length ? `Based on ${snapshot.market_indicators.length} market indicators.` : undefined,
      }
    case 'freshness':
      return {
        title: 'Freshness',
        summary:
          'Freshness shows how current the snapshot is, which directly affects how much trust to place in the methodology output.',
        bullets: [
          `Last update: ${freshness}.`,
          nextRefreshAt ? `Next scheduled refresh: ${formatDateTime(nextRefreshAt.toISOString())}.` : 'No refresh schedule is currently available.',
          'Stale inputs reduce confidence and should make you read the methodology with more caution.',
        ],
        footer: snapshot?.as_of ? `As of ${formatDateTime(snapshot.as_of)}.` : undefined,
      }
    default:
      return {
        title: 'Metric',
        summary: 'No metric details are available.',
        bullets: [],
      }
  }
}

function StatBlock({
  label,
  value,
  helper,
  onClick,
}: {
  label: string
  value: string
  helper?: string
  onClick?: () => void
}) {
  return (
    <Paper
      component={onClick ? 'button' : 'div'}
      type={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      variant="outlined"
      aria-haspopup={onClick ? 'dialog' : undefined}
      aria-label={onClick ? `${label} explanation` : undefined}
      onClick={onClick}
      sx={(theme) => ({
        p: 1.5,
        borderRadius: 3,
        background: alpha(theme.palette.background.paper, 0.92),
        textAlign: 'left',
        width: '100%',
        appearance: 'none',
        borderStyle: 'solid',
        cursor: onClick ? 'pointer' : 'default',
        '&:hover': onClick
          ? {
              borderColor: alpha(theme.palette.primary.main, 0.32),
              boxShadow: `0 10px 24px ${alpha(theme.palette.common.black, 0.05)}`,
            }
          : undefined,
        '&:focus-visible': onClick
          ? {
              borderColor: theme.palette.primary.main,
              boxShadow: `0 0 0 3px ${alpha(theme.palette.primary.main, 0.22)}`,
            }
          : undefined,
      })}
    >
      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {label}
        </Typography>
        <Typography variant="h6" sx={{ lineHeight: 1.1 }}>
          {value}
        </Typography>
        {helper ? (
          <Typography variant="caption" color="text.secondary">
            {helper}
          </Typography>
        ) : null}
        {onClick ? (
          <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: '0.04em' }}>
            View explanation
          </Typography>
        ) : null}
      </Stack>
    </Paper>
  )
}

function MetricDetailDialog({
  metric,
  snapshot,
  nextRefreshAt,
  open,
  onClose,
}: {
  metric: OverviewMetricKey | null
  snapshot: MarketOverviewSnapshot | null
  nextRefreshAt: Date | null
  open: boolean
  onClose: () => void
}) {
  const content = metric ? getMetricModalIntro(metric, snapshot, nextRefreshAt) : null
  const methodology = resolveMethodology(snapshot)

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      slotProps={{ paper: { sx: { overflow: 'hidden' } } }}
    >
      <DialogTitle
        sx={(theme) => ({
          pr: 6,
          pb: 1.25,
          background: `linear-gradient(135deg, ${alpha(theme.palette.secondary.main, 0.12)}, ${alpha(
            theme.palette.background.paper,
            1,
          )})`,
        })}
      >
        <Stack spacing={0.5}>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.16em' }}>
            Overview metric
          </Typography>
          <Typography variant="h6" component="div">
            {content?.title ? `${content.title} explanation` : 'Metric explanation'}
          </Typography>
        </Stack>
        <IconButton
          aria-label="Close metric details"
          onClick={onClose}
          sx={{ position: 'absolute', right: 16, top: 16 }}
        >
          <CloseRoundedIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 2.5, pb: 3 }}>
        {content ? (
          <Stack spacing={2}>
            <Typography variant="body1" sx={{ lineHeight: 1.7 }}>
              {content.summary}
            </Typography>

            <Stack component="ul" spacing={0.75} sx={{ m: 0, pl: 2.5 }}>
              {content.bullets.map((item) => (
                <Typography key={item} component="li" variant="body2" sx={{ lineHeight: 1.6 }}>
                  {item}
                </Typography>
              ))}
            </Stack>

            {content.footer ? (
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                {content.footer}
              </Typography>
            ) : null}

            <Divider />

            <Stack spacing={1.5}>
              <Typography variant="subtitle2" sx={{ letterSpacing: '0.04em' }}>
                Exact methodology
              </Typography>
              {renderMethodologySection(methodology)}
            </Stack>
          </Stack>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

function IndicatorCard({
  indicator,
  onOpen,
}: {
  indicator: MarketOverviewIndicator
  onOpen: (indicator: MarketOverviewIndicator) => void
}) {
  const tone = resolveTone(indicator.tone)
  const chipColor = toneColor(tone)
  const paletteKey = tonePaletteKey(tone)
  const explanation = indicator.explanation
  const hasExplanation = Boolean(
    explanation &&
      (explanation.summary ||
        explanation.inputs.length > 0 ||
        explanation.calculation_steps.length > 0 ||
        explanation.interpretation ||
        explanation.freshness ||
        explanation.caveats.length > 0),
  )

  return (
    <Paper
      component="button"
      type="button"
      tabIndex={0}
      aria-label={`${indicator.label} explanation`}
      aria-haspopup="dialog"
      onClick={() => onOpen(indicator)}
      variant="outlined"
      sx={(theme) => ({
        width: '100%',
        p: 2,
        borderRadius: 3,
        borderColor: tone === 'neutral' ? theme.palette.divider : alpha(theme.palette[paletteKey].main, 0.35),
        background:
          tone === 'neutral'
            ? alpha(theme.palette.background.paper, 0.95)
            : alpha(theme.palette[paletteKey].main, 0.06),
        cursor: hasExplanation ? 'pointer' : 'default',
        textAlign: 'left',
        appearance: 'none',
        outline: 'none',
        borderStyle: 'solid',
        '&:hover': hasExplanation
          ? {
              borderColor: alpha(theme.palette[paletteKey].main, 0.55),
              boxShadow: `0 10px 24px ${alpha(theme.palette.common.black, 0.06)}`,
            }
          : undefined,
        '&:focus-visible': {
          boxShadow: `0 0 0 3px ${alpha(theme.palette.primary.main, 0.25)}`,
          borderColor: theme.palette.primary.main,
        },
      })}
    >
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <Stack spacing={0.25} sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ lineHeight: 1.2 }}>
              {indicator.label}
            </Typography>
            {indicator.category ? (
              <Typography variant="caption" color="text.secondary">
                {titleize(indicator.category)}
              </Typography>
            ) : null}
          </Stack>
          <Chip label={indicator.key} size="small" variant="outlined" />
        </Stack>

        <Typography variant="h6" sx={{ lineHeight: 1.1 }}>
          {indicator.value}
        </Typography>

        {indicator.change ? (
          <Chip
            label={indicator.change}
            size="small"
            color={chipColor}
            variant={tone === 'neutral' ? 'outlined' : 'filled'}
            sx={{ alignSelf: 'flex-start' }}
          />
        ) : null}

        {indicator.note ? (
          <Typography variant="body2" color="text.secondary">
            {indicator.note}
          </Typography>
        ) : null}

        {hasExplanation ? null : (
          <Typography variant="caption" color="text.secondary" sx={{ pt: 0.25, letterSpacing: '0.04em' }}>
            No explanation available
          </Typography>
        )}
      </Stack>
    </Paper>
  )
}

function ProbabilityRow({ regime, probability }: { regime: string; probability: number }) {
  return (
    <Stack spacing={0.75}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {regime}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {formatProbability(probability)}
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={probability * 100}
        sx={(theme) => ({
          height: 8,
          borderRadius: 999,
          backgroundColor: alpha(theme.palette.primary.main, 0.12),
        })}
      />
    </Stack>
  )
}

function PillarCard({ pillar, value }: { pillar: string; value: unknown }) {
  const numericValue = typeof value === 'number' ? value : null
  const tone = scoreTone(value)
  const barValue = indicatorBarValue(value)
  const paletteKey = tonePaletteKey(tone)

  return (
    <Paper
      variant="outlined"
      sx={(theme) => ({
        p: 1.75,
        borderRadius: 3,
        background:
          numericValue == null
            ? alpha(theme.palette.background.paper, 0.8)
            : alpha(theme.palette[paletteKey].main, 0.05),
      })}
    >
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle2" sx={{ lineHeight: 1.2 }}>
            {titleize(pillar)}
          </Typography>
          <Chip
            label={scoreLabel(value)}
            size="small"
            color={toneColor(tone)}
            variant={numericValue == null ? 'outlined' : 'filled'}
          />
        </Stack>

        {barValue != null ? (
          <LinearProgress
            variant="determinate"
            value={barValue}
            sx={(theme) => ({
              height: 8,
              borderRadius: 999,
              backgroundColor: alpha(theme.palette.divider, 0.35),
            })}
          />
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>
            {formatValue(value)}
          </Typography>
        )}
      </Stack>
    </Paper>
  )
}

function DevelopmentCard({ item }: { item: Record<string, unknown> }) {
  const title = typeof item.title === 'string' ? item.title : typeof item.name === 'string' ? item.name : 'Development'
  const category = typeof item.category === 'string' ? item.category : null
  const importance = typeof item.importance_score === 'number' ? item.importance_score : null
  const reaction = isRecord(item.market_reaction)
    ? Object.entries(item.market_reaction)
        .map(([key, value]) => `${titleize(key)}: ${formatValue(value)}`)
        .join(' · ')
    : null

  return (
    <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 3 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle2" sx={{ lineHeight: 1.2 }}>
            {title}
          </Typography>
          {importance != null ? <Chip label={formatPercent(importance * 100)} size="small" color="info" /> : null}
        </Stack>
        {category ? (
          <Typography variant="caption" color="text.secondary">
            {titleize(category)}
          </Typography>
        ) : null}
        {reaction ? (
          <Typography variant="body2" color="text.secondary">
            {reaction}
          </Typography>
        ) : null}
        {typeof item.summary === 'string' ? (
          <Typography variant="body2">{item.summary}</Typography>
        ) : null}
      </Stack>
    </Paper>
  )
}

function LoadingSkeleton() {
  return (
    <Stack spacing={3}>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Skeleton variant="text" width="18%" height={24} />
          <Skeleton variant="text" width="72%" height={56} />
          <Skeleton variant="text" width="90%" height={28} />
          <Skeleton variant="rounded" width="100%" height={132} />
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' },
              gap: 1.5,
            }}
          >
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} variant="rounded" height={92} />
            ))}
          </Box>
        </Stack>
      </Paper>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' } }}>
        {Array.from({ length: 2 }).map((_, index) => (
          <Paper key={index} variant="outlined" sx={{ p: 2.5, borderRadius: 4 }}>
            <Stack spacing={1.5}>
              <Skeleton variant="text" width="30%" height={24} />
              <Skeleton variant="rounded" height={220} />
            </Stack>
          </Paper>
        ))}
      </Box>
    </Stack>
  )
}

export function MarketOverviewPage() {
  const { platformSettings } = useSettings()
  const [snapshot, setSnapshot] = useState<MarketOverviewSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [reloadNotice, setReloadNotice] = useState<string | null>(null)
  const [selectedIndicator, setSelectedIndicator] = useState<MarketOverviewIndicator | null>(null)
  const [selectedMetric, setSelectedMetric] = useState<OverviewMetricKey | null>(null)
  const reloadSessionRef = useRef(0)

  const refreshIntervalSeconds = platformSettings.platform_behavior.market_overview_refresh_interval_seconds
  const indicators = useMemo(() => resolveIndicators(snapshot), [snapshot])
  const methodology = useMemo(() => resolveMethodology(snapshot), [snapshot])
  const watchNext = useMemo(() => resolveWatchNext(snapshot, indicators, methodology), [snapshot, indicators, methodology])
  const sortedProbabilities = useMemo(
    () => Object.entries(snapshot?.probabilities ?? {}).sort((left, right) => right[1] - left[1]),
    [snapshot?.probabilities],
  )
  const hasSnapshot = snapshot !== null

  const nextRefreshAt =
    snapshot && !Number.isNaN(new Date(snapshot.updated_at).getTime())
      ? new Date(new Date(snapshot.updated_at).getTime() + refreshIntervalSeconds * 1000)
      : null

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setError(null)

    fetchLatestMarketOverview()
      .then((next) => {
        if (!cancelled) {
          setSnapshot(next)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load market overview')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleRefresh() {
    const sessionId = reloadSessionRef.current + 1
    reloadSessionRef.current = sessionId

    setRefreshing(true)
    setError(null)
    setReloadNotice('Reloading in the background...')
    try {
      const launch = await launchMarketOverview()
      for (;;) {
        if (reloadSessionRef.current !== sessionId) {
          return
        }

        const next = await fetchLatestMarketOverview()
        if (reloadSessionRef.current !== sessionId) {
          return
        }

        if (next.snapshot_id === launch.snapshot_id && isTerminalMarketOverviewStatus(next.status)) {
          setSnapshot(next)
          setReloadNotice('Reload complete')
          return
        }

        if (next.snapshot_id === launch.snapshot_id) {
          setReloadNotice('Reloading in the background...')
        }

        await sleep(OVERVIEW_RELOAD_POLL_INTERVAL_MS)
      }
    } catch (err) {
      if (reloadSessionRef.current === sessionId) {
        setError(err instanceof Error ? err.message : 'Failed to launch market overview')
        setReloadNotice(null)
      }
    } finally {
      if (reloadSessionRef.current === sessionId) {
        setRefreshing(false)
      }
    }
  }

  const stale = isStale(snapshot)
  const metricCards: OverviewMetricDefinition[] = [
    {
      key: 'confidence',
      label: 'Confidence',
      value: formatPercent(snapshot?.confidence ?? 0),
      helper: 'Probability gap and signal agreement',
    },
    {
      key: 'fragility',
      label: 'Fragility',
      value: formatPercent(snapshot?.fragility ?? 0),
      helper: 'Vulnerability to a shock despite current trend',
    },
    {
      key: 'contradiction',
      label: 'Contradiction',
      value: formatPercent(snapshot?.contradiction_score ?? 0),
      helper: 'How much the signals disagree',
    },
    {
      key: 'freshness',
      label: 'Freshness',
      value: snapshot?.updated_at ? formatRelativeMinutes(snapshot.updated_at) : '—',
      helper: snapshot?.as_of ? `As of ${formatDateTime(snapshot.as_of)}` : 'No as-of timestamp',
    },
  ]

  return (
    <Stack spacing={3}>
      <Stack spacing={0.75}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.16em' }}>
          Market Overview
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: '72ch' }}>
          A financial front page for the current regime read, the signals beneath it, and the
          logic that shapes the summary.
        </Typography>
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      <IndicatorExplanationDialog
        indicator={selectedIndicator}
        open={selectedIndicator !== null}
        onClose={() => setSelectedIndicator(null)}
      />

      <MetricDetailDialog
        metric={selectedMetric}
        snapshot={snapshot}
        nextRefreshAt={nextRefreshAt}
        open={selectedMetric !== null}
        onClose={() => setSelectedMetric(null)}
      />

      {loading && !hasSnapshot ? (
        <LoadingSkeleton />
      ) : (
        <Stack spacing={3}>
          <Paper
            variant="outlined"
            sx={(paperTheme) => ({
              p: { xs: 2.5, md: 3 },
              borderRadius: 5,
              position: 'relative',
              overflow: 'hidden',
              color: paperTheme.palette.text.primary,
              background:
                paperTheme.palette.mode === 'dark'
                  ? `linear-gradient(135deg, ${alpha(paperTheme.palette.background.paper, 0.98)}, ${alpha(
                      paperTheme.palette.primary.main,
                      0.1,
                    )})`
                  : `linear-gradient(135deg, ${alpha('#ffffff', 0.98)}, ${alpha(
                      paperTheme.palette.primary.main,
                      0.06,
                    )})`,
              boxShadow:
                paperTheme.palette.mode === 'dark'
                  ? `0 22px 60px ${alpha(paperTheme.palette.common.black, 0.24)}`
                  : `0 18px 40px ${alpha(paperTheme.palette.primary.main, 0.08)}`,
              '&::before': {
                content: '""',
                position: 'absolute',
                inset: 0,
                pointerEvents: 'none',
                background:
                  paperTheme.palette.mode === 'dark'
                    ? 'radial-gradient(circle at top right, rgba(255,255,255,0.10), transparent 26%), radial-gradient(circle at bottom left, rgba(255,255,255,0.04), transparent 28%)'
                    : 'radial-gradient(circle at top right, rgba(108,184,255,0.18), transparent 26%), radial-gradient(circle at bottom left, rgba(34,211,238,0.12), transparent 28%)',
              },
            })}
          >
            <Box sx={{ position: 'relative', zIndex: 1 }}>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.5fr) minmax(320px, 0.75fr)' },
                  gap: 3,
                }}
              >
                <Stack spacing={2.25}>
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                      <Chip label={snapshot?.status ?? 'loading'} color="primary" />
                      {stale ? <Chip label="Stale" color="warning" variant="outlined" /> : null}
                      <Chip
                        label={`Updated ${formatRelativeMinutes(snapshot?.updated_at)}`}
                        variant="outlined"
                      />
                    </Stack>
                    <Typography variant="h3" component="h1" sx={{ letterSpacing: '-0.04em' }}>
                      {snapshot?.top_regime ?? 'Loading overview…'}
                    </Typography>
                    <Typography variant="h6" component="p" sx={{ fontWeight: 500, maxWidth: '70ch' }}>
                      {snapshot?.summary_text ?? 'Waiting for the latest market snapshot.'}
                    </Typography>
                  </Stack>

                  <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                    <Button
                      variant="contained"
                      startIcon={<RefreshRoundedIcon />}
                      onClick={() => void handleRefresh()}
                      disabled={refreshing || loading}
                    >
                      {refreshing ? 'Reloading…' : 'Reload overview'}
                    </Button>
                    <Typography variant="body2" color="text.secondary">
                      {snapshot?.argo_workflow_name ? `Workflow ${snapshot.argo_workflow_name}` : 'No workflow recorded yet'}
                    </Typography>
                    {reloadNotice ? (
                      <Typography variant="caption" color="text.secondary" sx={{ width: '100%' }}>
                        {reloadNotice}
                      </Typography>
                    ) : null}
                  </Stack>
                </Stack>

                <Stack spacing={1.5}>
                  {metricCards.map((metric) => (
                    <StatBlock
                      key={metric.key}
                      label={metric.label}
                      value={metric.value}
                      helper={metric.helper}
                      onClick={() => setSelectedMetric(metric.key)}
                    />
                  ))}
                </Stack>
              </Box>
            </Box>
          </Paper>

          <SectionCard
            title="Market tape"
            subtitle="Core indices, breadth, and cross-asset context that sit beneath the regime label."
          >
            {indicators.length === 0 ? (
              <Alert severity="info">No structured market indicators are available yet.</Alert>
            ) : (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: {
                    xs: '1fr',
                    sm: 'repeat(2, minmax(0, 1fr))',
                    lg: 'repeat(3, minmax(0, 1fr))',
                    xl: 'repeat(4, minmax(0, 1fr))',
                  },
                  gap: 1.5,
                }}
              >
                {indicators.map((indicator) => (
                  <IndicatorCard
                    key={indicator.key}
                    indicator={indicator}
                    onOpen={(nextIndicator) => setSelectedIndicator(nextIndicator)}
                  />
                ))}
              </Box>
            )}
          </SectionCard>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1.15fr) minmax(360px, 0.85fr)' },
              gap: 2,
              alignItems: 'start',
            }}
          >
            <Stack spacing={2}>
              <SectionCard title="Probability distribution" subtitle="Relative likelihood across the plausible regime set.">
                {sortedProbabilities.length === 0 ? (
                  <Typography color="text.secondary">No probability distribution is available yet.</Typography>
                ) : (
                  <Stack spacing={1.75}>
                    {sortedProbabilities.map(([regime, probability]) => (
                      <ProbabilityRow key={regime} regime={regime} probability={probability} />
                    ))}
                  </Stack>
                )}
              </SectionCard>

              <SectionCard title="What changed" subtitle="The short read on why the market moved the way it did.">
                <Stack spacing={2}>
                  <Typography variant="body1" sx={{ lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                    {snapshot?.summary_text ?? 'No summary text is available yet.'}
                  </Typography>

                  <Divider />

                  {snapshot && Object.keys(snapshot.freshness).length > 0 ? (
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
                        gap: 1.25,
                      }}
                    >
                      {Object.entries(snapshot.freshness).map(([key, value]) => (
                        <Paper key={key} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                          <Stack spacing={0.5}>
                            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                              {titleize(key)}
                            </Typography>
                            <Typography variant="body2">{formatValue(value)}</Typography>
                          </Stack>
                        </Paper>
                      ))}
                    </Box>
                  ) : (
                    <Typography color="text.secondary">
                      No freshness metadata was supplied with this snapshot.
                    </Typography>
                  )}
                </Stack>
              </SectionCard>

              <SectionCard title="Recent developments" subtitle="Impact-ranked developments that changed the market backdrop.">
                {snapshot?.developments.length === 0 ? (
                  <Typography color="text.secondary">No recent developments recorded.</Typography>
                ) : (
                  <Stack spacing={1.25}>
                    {snapshot?.developments.map((item, index) => (
                      <DevelopmentCard key={index} item={item} />
                    ))}
                  </Stack>
                )}
              </SectionCard>

              <SectionCard title="Pillar scores" subtitle="The component scores that feed the regime engine.">
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
                    gap: 1.5,
                  }}
                >
                  {Object.entries(snapshot?.pillar_scores ?? {}).map(([pillar, value]) => (
                    <PillarCard key={pillar} pillar={pillar} value={value} />
                  ))}
                </Box>
              </SectionCard>
            </Stack>

            <Stack spacing={2}>
              <SectionCard title="How it’s computed" subtitle="Plain-English explanation of the regime logic.">
                {renderMethodologySection(methodology)}
              </SectionCard>

              <SectionCard title="Watch next" subtitle="Signals and catalysts to keep an eye on from here.">
                {watchNext.length === 0 ? (
                  <Typography color="text.secondary">No watch-next signals are available yet.</Typography>
                ) : (
                  <Stack spacing={1.25}>
                    {watchNext.map((item) => (
                      <Paper key={item} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                          {item}
                        </Typography>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </SectionCard>
            </Stack>
          </Box>
        </Stack>
      )}
    </Stack>
  )
}
