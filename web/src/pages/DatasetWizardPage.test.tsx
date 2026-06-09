import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'

const createDatasetMock = vi.hoisted(() => vi.fn())
const navigateMock = vi.hoisted(() => vi.fn())
const fetchUniversesMock = vi.hoisted(() => vi.fn())
const fetchUniverseConstituentsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  createDataset: createDatasetMock,
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
})
