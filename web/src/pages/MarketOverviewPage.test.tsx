import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { within } from '@testing-library/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchLatestMarketOverviewMock = vi.hoisted(() => vi.fn())
const launchMarketOverviewMock = vi.hoisted(() => vi.fn())

vi.mock('../api/marketOverview', () => ({
  fetchLatestMarketOverview: fetchLatestMarketOverviewMock,
  launchMarketOverview: launchMarketOverviewMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        market_overview_refresh_interval_seconds: 60,
      },
    },
  }),
}))

import { MarketOverviewPage } from './MarketOverviewPage'

const baseSnapshot = {
  snapshot_id: 'snap-1',
  name: 'Morning regime',
  status: 'completed',
  argo_namespace: 'market',
  argo_workflow_name: 'market-overview-snap-1',
  as_of: '2026-06-08T08:30:00.000Z',
  top_regime: 'Risk-On',
  probabilities: {
    'Risk-On': 0.62,
    Neutral: 0.22,
    'Risk-Off': 0.16,
  },
  confidence: 72,
  fragility: 18,
  contradiction_score: 12,
  market_indicators: [
    {
      key: 'breadth',
      label: 'Breadth',
      value: 'Strong',
      change: '+1.2',
      tone: 'positive',
      category: 'market tape',
      note: 'Advance/decline remains constructive.',
      explanation: {
        summary: 'Breadth improved across the major equity composites.',
        inputs: ['Advance/decline line', 'New highs vs. new lows'],
        calculation_steps: ['Compare current breadth to the 20-day median.', 'Weight breadth together with index trend.'],
        interpretation: 'Participation is broad enough to support the current regime.',
        freshness: 'Updated within the last hour.',
        caveats: ['Breadth can fade quickly if leadership narrows.'],
      },
    },
  ],
  pillar_scores: { trend: 1.2 },
  developments: [],
  freshness: { tape: 'fresh' },
  summary_text: 'The market is broad and the trend is intact.',
  watch_next: ['Watch participation'],
  methodology: {
    summary: 'Methodology summary.',
    inputs: ['Equity breadth'],
    scoring: ['Score breadth against trend.'],
    freshness: 'Fresh data matters.',
    caveats: ['Probabilistic, not deterministic.'],
  },
  evidence: {},
  params: {},
  error_message: null,
  created_at: '2026-06-08T08:30:00.000Z',
  updated_at: '2026-06-08T08:30:00.000Z',
}

describe('MarketOverviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchLatestMarketOverviewMock.mockResolvedValue(baseSnapshot)
    launchMarketOverviewMock.mockResolvedValue({
      snapshot_id: 'snap-2',
      status: 'running',
      argo_namespace: 'market',
      argo_workflow_name: 'market-overview-snap-2',
    })
  })

  it('opens indicator explanations in a dedicated dialog', async () => {
    render(<MarketOverviewPage />)

    await screen.findByRole('heading', { name: 'Risk-On' })
    fireEvent.click(screen.getByRole('button', { name: /breadth explanation/i }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Breadth improved across the major equity composites.')).toBeInTheDocument()
    expect(within(dialog).getByText('Inputs')).toBeInTheDocument()
    expect(within(dialog).getByText('Computation')).toBeInTheDocument()
  })

  it('clears the current overview before reloading fresh data', async () => {
    const runningSnapshot = {
      ...baseSnapshot,
      snapshot_id: 'snap-2',
      status: 'running',
      summary_text: 'The market is still being recalculated.',
      updated_at: '2026-06-08T08:31:00.000Z',
    }
    const completedSnapshot = {
      ...runningSnapshot,
      snapshot_id: 'snap-2',
      status: 'completed',
      summary_text: 'Reloaded overview is now complete.',
      updated_at: '2026-06-08T08:32:00.000Z',
    }

    fetchLatestMarketOverviewMock
      .mockResolvedValueOnce(baseSnapshot)
      .mockResolvedValueOnce(runningSnapshot)
      .mockResolvedValueOnce(completedSnapshot)

    render(<MarketOverviewPage />)

    await screen.findByRole('heading', { name: 'Risk-On' })
    fireEvent.click(screen.getByRole('button', { name: /reload overview/i }))

    expect(screen.getByRole('heading', { name: 'Risk-On' })).toBeInTheDocument()
    expect(screen.getByText('Reloading in the background...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reloading/i })).toBeDisabled()

    await waitFor(() => {
      expect(screen.getAllByText('Reloaded overview is now complete.').length).toBeGreaterThan(0)
    }, { timeout: 3000 })
    expect(launchMarketOverviewMock).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['confidence', /confidence explanation/i, /confidence: 72%/i, /confidence explanation/i],
    ['fragility', /fragility explanation/i, /fragility: 18%/i, /fragility explanation/i],
    ['contradiction', /contradiction explanation/i, /contradiction score: 12%/i, /contradiction explanation/i],
    ['freshness', /freshness explanation/i, /last update:/i, /freshness explanation/i],
  ])('opens the %s card in its own explanation modal', async (_metric, triggerName, bodyText, headingName) => {
    render(<MarketOverviewPage />)

    await waitFor(() => {
      expect(screen.getAllByRole('heading', { name: 'Risk-On' }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('button', { name: triggerName }).length).toBeGreaterThan(0)
    })
    fireEvent.click(screen.getAllByRole('button', { name: triggerName })[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: headingName })).toBeInTheDocument()
    expect(within(dialog).getByText(bodyText)).toBeInTheDocument()
    expect(within(dialog).getByText(baseSnapshot.methodology.summary)).toBeInTheDocument()
    expect(within(dialog).getByText('Inputs')).toBeInTheDocument()
    expect(within(dialog).getByText('Scoring')).toBeInTheDocument()
    expect(within(dialog).getByText(baseSnapshot.methodology.freshness as string)).toBeInTheDocument()
    expect(within(dialog).getByText(baseSnapshot.methodology.caveats[0])).toBeInTheDocument()
  })
})
