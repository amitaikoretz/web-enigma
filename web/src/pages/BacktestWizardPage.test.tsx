// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { defaultPlatformSettings } from '../settings/defaults'

const createBacktestMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  createBacktest: createBacktestMock,
  fetchBacktestInputConfig: vi.fn(),
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

vi.mock('../api/riskModels', () => ({
  fetchRiskModels: vi.fn().mockResolvedValue([
    {
      group_id: 'risk-1',
      name: 'Risk model 1',
      status: 'succeeded',
      targets: ['stop_prob'],
      targets_total: 1,
      targets_done: 1,
      created_at: '2024-02-01T00:00:00Z',
      updated_at: '2024-02-01T00:00:00Z',
      feature_run_id: null,
      argo_namespace: null,
      argo_workflow_name: null,
      summary_metrics: null,
    },
  ]),
}))

vi.mock('../api/strategies', () => ({
  fetchStrategies: vi.fn().mockResolvedValue([
    {
      name: 'buy_and_hold',
      description: 'demo',
      documentation: 'doc',
      parameters: {},
    },
  ]),
  fetchExitRules: vi.fn().mockResolvedValue([
    {
      name: 'fixed_pct_oco',
      description: 'demo',
      documentation: 'doc',
      parameters: {},
    },
  ]),
}))

vi.mock('../api/universes', () => ({
  fetchUniverses: vi.fn().mockResolvedValue([]),
  fetchUniverseConstituents: vi.fn(),
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

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/backtests/new']}>
      <LocalizationProvider dateAdapter={AdapterDayjs}>
        <Routes>
          <Route path="/backtests/new" element={<BacktestWizardPage />} />
        </Routes>
      </LocalizationProvider>
    </MemoryRouter>,
  )
}

describe('BacktestWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.scrollTo = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders a multi-step wizard with classic and vector bt type choices', async () => {
    renderPage()

    expect(await screen.findByText('Backtest Wizard')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Classic backtest/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Vector bt/i })).toBeInTheDocument()
  })

  it('submits a classic payload through the review step', async () => {
    createBacktestMock.mockResolvedValueOnce({ backtest_id: 'bt-1', status: 'pending', status_url: '/x', detail_url: '/y' })

    renderPage()

    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByLabelText('Data source')
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByLabelText('Triggers')
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByText('Type: Classic backtest')
    fireEvent.click(screen.getByRole('button', { name: 'Launch backtest' }))

    await waitFor(() => expect(createBacktestMock).toHaveBeenCalledTimes(1))
    expect(createBacktestMock).toHaveBeenCalledWith(
      expect.objectContaining({
        backtest_type: 'classic',
        resolution: '1d',
        feed: 'iex',
        triggers: expect.any(Array),
        exit_rules: expect.any(Array),
      }),
    )
  })

  it('submits a vector bt payload with dataset and risk model selections', async () => {
    createBacktestMock.mockResolvedValueOnce({ backtest_id: 'bt-2', status: 'running', status_url: '/x', detail_url: '/y' })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Vector bt/i }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])

    const datasetField = await screen.findByLabelText('Completed dataset')
    fireEvent.mouseDown(datasetField)
    fireEvent.click(await screen.findByText(/ds-1/i))

    const riskField = screen.getByLabelText('Risk model group')
    fireEvent.mouseDown(riskField)
    fireEvent.click(await screen.findByText('risk-1'))

    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByText('Vector bt configuration')
    fireEvent.change(screen.getByLabelText('Risk threshold'), { target: { value: '0.6' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByText('Type: Vector bt')
    fireEvent.click(screen.getByRole('button', { name: 'Launch backtest' }))

    await waitFor(() => expect(createBacktestMock).toHaveBeenCalledTimes(1))
    expect(createBacktestMock).toHaveBeenCalledWith(
      expect.objectContaining({
        backtest_type: 'vectorbt',
        dataset_id: 'ds-1',
        risk_model: { group_id: 'risk-1' },
        risk_threshold: 0.6,
      }),
    )
  })

  it('allows an ungated vector bt payload when no risk model is chosen', async () => {
    createBacktestMock.mockResolvedValueOnce({ backtest_id: 'bt-3', status: 'running', status_url: '/x', detail_url: '/y' })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Vector bt/i }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])

    const datasetField = await screen.findByLabelText('Completed dataset')
    fireEvent.mouseDown(datasetField)
    fireEvent.click(await screen.findByText(/ds-1/i))

    expect(screen.getByText(/will be submitted as an ungated vector bt backtest/i)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByText('Vector bt configuration')
    expect(screen.getByLabelText('Risk threshold')).toBeDisabled()
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByText('Risk model: Ungated')
    fireEvent.click(screen.getByRole('button', { name: 'Launch backtest' }))

    await waitFor(() => expect(createBacktestMock).toHaveBeenCalledTimes(1))
    expect(createBacktestMock).toHaveBeenCalledWith(
      expect.objectContaining({
        backtest_type: 'vectorbt',
        dataset_id: 'ds-1',
        risk_model: null,
      }),
    )
  })

  it('blocks moving past vector bt data step until a dataset is chosen', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Vector bt/i }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])
    await screen.findByLabelText('Completed dataset')
    fireEvent.click(screen.getAllByRole('button', { name: 'Continue' })[0])

    expect(await screen.findByText('Choose a completed dataset for the vector bt run.')).toBeInTheDocument()
  })
})
