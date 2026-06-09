// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import dayjs from 'dayjs'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { defaultPlatformSettings } from '../settings/defaults'

const createBacktestMock = vi.hoisted(() => vi.fn())
const fetchUniverseConstituentsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  createBacktest: createBacktestMock,
  fetchBacktestInputConfig: vi.fn(),
}))

vi.mock('../api/universes', () => ({
  fetchUniverses: vi.fn().mockResolvedValue([
    {
      key: 'sp500',
      kind: 'registry',
      name: 'S&P 500',
      description: 'Large cap US equities',
      provider: 'static',
      provider_ref: { symbols: ['AAPL', 'MSFT', 'NVDA'] },
      is_active: true,
      latest_refresh_status: 'completed',
      latest_refresh_started_at: null,
      latest_refresh_as_of: null,
    },
  ]),
  fetchUniverseConstituents: fetchUniverseConstituentsMock,
}))

vi.mock('../api/datasets', () => ({
  fetchDatasets: vi.fn().mockResolvedValue({
    items: [
      {
        id: 'ds-1',
        name: 'My dataset',
        symbol: 'AAPL',
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        created_at: '2024-02-01T00:00:00Z',
        updated_at: '2024-02-01T00:00:00Z',
        status: 'completed',
        argo_namespace: null,
        argo_workflow_name: null,
        output_dir: '/tmp',
        dataset_parquet_path: '/tmp/dataset.parquet',
        manifest_path: '/tmp/dataset.manifest.json',
        options_parquet_path: null,
        options_manifest_path: null,
        error_message: null,
        progress_pct: 100,
      },
    ],
    total: 1,
    page: 1,
    page_size: 1,
  }),
}))

vi.mock('../api/strategies', () => ({
  fetchStrategies: vi.fn().mockResolvedValue([
    {
      name: 'buy_and_hold',
      description: 'demo',
      documentation: 'This trigger enters long on the first bar it sees.',
      parameters: {},
    },
  ]),
  fetchExitRules: vi.fn().mockResolvedValue([
    {
      name: 'fixed_pct_oco',
      description: 'demo',
      documentation: 'Exit rule docs',
      parameters: {},
    },
  ]),
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      ...defaultPlatformSettings,
      backtest_defaults: {
        ...defaultPlatformSettings.backtest_defaults,
        resolution: '1d',
        feed: 'iex',
        broker: { cash: 10000, commission: 0, slippage_perc: 0.0005, sizer: 'fixed' },
        analyzers: {
          include_equity_curve: true,
          include_trade_log: true,
          include_order_log: true,
          include_candidate_log: false,
          include_risk_auxiliary: false,
        },
        execution: { fill_model: 'close' },
        symbols_seed_list: ['AAPL'],
        date_range_preset: '30D',
      },
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        confirm_before_launch: false,
      },
    },
  }),
}))

import { BacktestWizardPage } from './BacktestWizardPage'

describe('BacktestWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.scrollTo = vi.fn()
  })

  it('toggles between legacy selection and dataset-backed launch modes', async () => {
    fetchUniverseConstituentsMock.mockResolvedValue({
      key: 'sp500',
      as_of: '2026-06-08',
      symbols: ['MSFT', 'NVDA'],
    })

    render(
      <MemoryRouter initialEntries={['/backtests/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/new" element={<BacktestWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Back to results' })).toHaveAttribute('href', '/backtests')
    expect(await screen.findByText('Legacy selection')).toBeInTheDocument()
    expect(screen.getByLabelText('Universe')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sample from universe' })).toBeInTheDocument()
    expect(screen.getByLabelText('Symbols')).toBeInTheDocument()
    expect(screen.getAllByText('Start date').length).toBeGreaterThan(0)
    expect(screen.queryByLabelText('Existing dataset')).not.toBeInTheDocument()

    fireEvent.mouseDown(screen.getByLabelText('Universe'))
    fireEvent.click(await screen.findByText('S&P 500 (sp500)'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sample from universe' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Sample from universe' }))

    await waitFor(() =>
      expect(fetchUniverseConstituentsMock).toHaveBeenCalledWith(
        'sp500',
        dayjs().subtract(30, 'day').format('YYYY-MM-DD'),
      ),
    )
    await waitFor(() => expect(screen.getByText('MSFT')).toBeInTheDocument())
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('switch', { name: 'Use legacy selection' }))

    await waitFor(() => expect(screen.getByLabelText('Existing dataset')).toBeInTheDocument())
    expect(screen.queryByLabelText('Symbols')).not.toBeInTheDocument()
    expect(screen.queryByText('Start date')).not.toBeInTheDocument()
  })

  it('scrolls the error alert into view when backtest submission fails', async () => {
    createBacktestMock.mockRejectedValueOnce(new Error('Launch failed'))

    render(
      <MemoryRouter initialEntries={['/backtests/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/new" element={<BacktestWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    expect(screen.getAllByRole('heading', { name: 'Legacy selection' }).length).toBeGreaterThan(0)
    await waitFor(() =>
      expect(
        screen.getAllByRole('button', { name: 'Launch backtest' }).some((button) => !button.hasAttribute('disabled')),
      ).toBe(true),
    )
    fireEvent.click(screen.getAllByRole('button', { name: 'Launch backtest' }).find((button) => !button.hasAttribute('disabled'))!)

    expect(await screen.findByRole('alert')).toBeVisible()
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })

  it('opens trigger documentation from the wizard', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/new" element={<BacktestWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    const docsButton = await screen.findByRole('button', {
      name: 'Open documentation for buy_and_hold',
    })
    fireEvent.click(docsButton)

    expect(await screen.findByText('buy_and_hold documentation')).toBeInTheDocument()
    expect(screen.getByText(/enters long on the first bar/i)).toBeInTheDocument()
  })
})
