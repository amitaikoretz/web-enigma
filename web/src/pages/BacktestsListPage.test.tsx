import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const fetchBacktestsMock = vi.hoisted(() => vi.fn())
const deleteBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestForceMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  deleteBacktest: deleteBacktestMock,
  fetchBacktests: fetchBacktestsMock,
  retryBacktest: retryBacktestMock,
  retryBacktestForce: retryBacktestForceMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
      backtest_defaults: {
        results_table_columns: ['status'],
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { BacktestsListPage } from './BacktestsListPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{JSON.stringify({ pathname: location.pathname, state: location.state })}</div>
}

describe('BacktestsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchBacktestsMock.mockResolvedValue({
      items: [
        {
          id: 'bt-1',
          created_at: '2026-06-01T12:00:00.000Z',
          updated_at: '2026-06-01T12:01:00.000Z',
          status: 'succeeded',
          selection: null,
        },
      ],
      total: 1,
    })
  })

  function clickBacktestSelection(backtestId: string) {
    const label = screen.getByLabelText(`Select backtest ${backtestId}`)
    const input = label.querySelector('input')
    if (!input) {
      throw new Error(`Checkbox input not found for ${backtestId}`)
    }
    fireEvent.click(input)
  }

  it('deep-links selected backtests into the risk wizard route', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests']}>
        <Routes>
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/models/risk/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByLabelText('Select backtest bt-1')
    clickBacktestSelection('bt-1')
    fireEvent.click(screen.getByRole('button', { name: /train risk model/i }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/models/risk/new')
    expect(screen.getByTestId('location')).toHaveTextContent('"sourceKind":"backtest"')
    expect(screen.getByTestId('location')).toHaveTextContent('"selectedCount":1')
  })

  it('deep-links selected backtests into the return forecast wizard route', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests']}>
        <Routes>
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/models/returns/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByLabelText('Select backtest bt-1')
    clickBacktestSelection('bt-1')
    fireEvent.click(screen.getByRole('button', { name: /train return forecast/i }))

    const locations = screen.getAllByTestId('location')
    expect(locations[1]).toHaveTextContent('/models/returns/new')
    expect(locations[1]).toHaveTextContent('"sourceKind":"backtest"')
    expect(locations[1]).toHaveTextContent('"selectedCount":1')
  })
})
