import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'

const createDatasetMock = vi.hoisted(() => vi.fn())
const navigateMock = vi.hoisted(() => vi.fn())
const fetchDatasetDetailMock = vi.hoisted(() => vi.fn())
const fetchUniversesMock = vi.hoisted(() => vi.fn())
const fetchUniverseConstituentsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  createDataset: createDatasetMock,
  fetchDatasetDetail: fetchDatasetDetailMock,
}))

vi.mock('../api/universes', () => ({
  fetchUniverses: fetchUniversesMock,
  fetchUniverseConstituents: fetchUniverseConstituentsMock,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      backtest_defaults: {
        symbols_seed_list: ['AAPL'],
        resolution: '1d',
      },
    },
  }),
}))

import { DatasetWizardPage } from './DatasetWizardPage'

describe('DatasetWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    navigateMock.mockReset()
    fetchDatasetDetailMock.mockResolvedValue({
      metadata: {
        id: 'source-ds-1',
        name: 'Source dataset',
        symbol: 'AAPL',
        symbols: ['AAPL', 'MSFT'],
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-04-01',
        end_date: '2026-05-01',
        created_at: '2026-06-07T00:00:00Z',
        updated_at: '2026-06-07T00:00:00Z',
        status: 'completed',
        argo_namespace: null,
        argo_workflow_name: null,
        params_json: {
          symbol: 'AAPL',
          symbols: ['AAPL', 'MSFT'],
          max_symbols_per_shard: 7,
          provider: 'alpaca',
          resolution: '1d',
          start_date: '2026-04-01',
          end_date: '2026-05-01',
          name: 'Source dataset',
          options: {
            enabled: true,
            feed: 'opra',
          },
        },
        output_dir: '/tmp/datasets',
        dataset_parquet_path: '/tmp/datasets/source.parquet',
        manifest_path: '/tmp/datasets/source.manifest.json',
        options_parquet_path: '/tmp/datasets/source-options.parquet',
        options_manifest_path: '/tmp/datasets/source-options.manifest.json',
        error_message: null,
        progress_pct: 100,
      },
    })
    fetchUniversesMock.mockResolvedValue([
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
    ])
    fetchUniverseConstituentsMock.mockResolvedValue({
      key: 'sp500',
      as_of: '2026-05-09',
      symbols: ['MSFT', 'NVDA'],
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('lets users pick a symbol from a selected universe before submitting the dataset workflow', async () => {
    createDatasetMock.mockResolvedValue({
      dataset_id: 'ds-1',
      status: 'pending',
      status_url: '/api/datasets/ds-1/status',
      detail_url: '/backtests/datasets/ds-1',
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/datasets/new" element={<DatasetWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Back to datasets' })).toHaveAttribute('href', '/backtests/datasets')
    fireEvent.click(screen.getByRole('button', { name: /sample from universe/i }))

    fireEvent.mouseDown(screen.getByLabelText('Universe'))
    fireEvent.click(await screen.findByText('S&P 500 (sp500)'))
    await waitFor(() => expect(fetchUniverseConstituentsMock).toHaveBeenCalledWith('sp500', expect.any(String)))
    await waitFor(() => expect(screen.getByRole('button', { name: /^sample symbols$/i })).not.toBeDisabled())
    fireEvent.change(screen.getByRole('slider'), { target: { value: 2 } })
    fireEvent.click(screen.getByRole('button', { name: /^sample symbols$/i }))

    await waitFor(() => expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0))
    expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /^close$/i }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Sample from universe' })).not.toBeInTheDocument())

    await waitFor(() => expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: /launch dataset/i }))

    expect(screen.getByText('Launch dataset?')).toBeInTheDocument()
    expect(createDatasetMock).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/dataset name/i), { target: { value: 'My dataset' } })
    fireEvent.click(screen.getByLabelText(/include options data/i))

    fireEvent.click(within(screen.getByRole('dialog', { name: 'Launch dataset?' })).getByRole('button', { name: /^launch dataset$/i }))

    await waitFor(() =>
      expect(createDatasetMock).toHaveBeenCalledWith({
        symbol: 'AAPL',
        symbols: ['AAPL', 'MSFT', 'NVDA'],
        max_symbols_per_shard: 10,
        provider: 'alpaca',
        resolution: '1d',
        start_date: expect.any(String),
        end_date: expect.any(String),
        name: 'My dataset',
        options: {
          enabled: true,
          feed: 'indicative',
        },
      }),
    )

    expect(await screen.findByText('Dataset launched')).toBeInTheDocument()
    expect(screen.getByText('Dataset launch submitted successfully.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dataset ds-1/i })).toHaveAttribute(
      'href',
      '/backtests/datasets/ds-1',
    )
  })

  it('reports launch errors in the result modal', async () => {
    createDatasetMock.mockRejectedValue(new Error('Failed to submit Argo workflow: 400 missing group-id'))

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/datasets/new" element={<DatasetWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getAllByRole('button', { name: /launch dataset/i })[0])
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Launch dataset?' })).getByRole('button', { name: /^launch dataset$/i }))

    await waitFor(() => expect(createDatasetMock).toHaveBeenCalled())

    expect(await screen.findByText('Dataset launch failed')).toBeInTheDocument()
    expect(screen.getByText('Failed to submit Argo workflow: 400 missing group-id')).toBeInTheDocument()
  })

  it('prefills from an existing dataset and submits an edited copy', async () => {
    createDatasetMock.mockResolvedValue({
      dataset_id: 'ds-2',
      status: 'pending',
      status_url: '/api/datasets/ds-2/status',
      detail_url: '/backtests/datasets/ds-2',
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/new?from=source-ds-1']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/datasets/new" element={<DatasetWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Prefilled from dataset source-ds-1. Edit any field before launching.',
      ),
    )

    fireEvent.change(screen.getByLabelText(/dataset name/i), { target: { value: 'Edited dataset' } })
    fireEvent.click(screen.getByRole('button', { name: /launch dataset/i }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Launch dataset?' })).getByRole('button', { name: /^launch dataset$/i }))

    await waitFor(() =>
      expect(createDatasetMock).toHaveBeenCalledWith({
        symbol: 'AAPL',
        symbols: ['AAPL', 'MSFT'],
        max_symbols_per_shard: 7,
        provider: 'alpaca',
        resolution: '1d',
        start_date: '2026-04-01',
        end_date: '2026-05-01',
        name: 'Edited dataset',
        options: {
          enabled: true,
          feed: 'opra',
        },
      }),
    )
    expect(await screen.findByText('Dataset launched')).toBeInTheDocument()
  })

  it('shows a default shard cap of 10 for new launches', async () => {
    createDatasetMock.mockResolvedValue({
      dataset_id: 'ds-3',
      status: 'pending',
      status_url: '/api/datasets/ds-3/status',
      detail_url: '/backtests/datasets/ds-3',
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets/new']}>
        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Routes>
            <Route path="/backtests/datasets/new" element={<DatasetWizardPage />} />
          </Routes>
        </LocalizationProvider>
      </MemoryRouter>,
    )

    expect(screen.getByLabelText(/max symbols per shard/i)).toHaveValue(10)

    fireEvent.click(screen.getAllByRole('button', { name: /launch dataset/i })[0])
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Launch dataset?' })).getByRole('button', { name: /^launch dataset$/i }))

    await waitFor(() =>
      expect(createDatasetMock).toHaveBeenCalledWith(
        expect.objectContaining({
          max_symbols_per_shard: 10,
        }),
      ),
    )
  })
})
