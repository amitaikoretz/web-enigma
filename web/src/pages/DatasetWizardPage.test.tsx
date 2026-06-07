import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'

const createDatasetMock = vi.hoisted(() => vi.fn())
const navigateMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  createDataset: createDatasetMock,
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
  })

  it('asks for confirmation before submitting the dataset workflow', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: /launch dataset/i }))

    expect(screen.getByText('Launch dataset?')).toBeInTheDocument()
    expect(createDatasetMock).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/dataset name/i), { target: { value: 'My dataset' } })
    fireEvent.click(screen.getByLabelText(/include options data/i))

    fireEvent.click(within(screen.getByRole('dialog', { name: 'Launch dataset?' })).getByRole('button', { name: /^launch dataset$/i }))

    await waitFor(() =>
      expect(createDatasetMock).toHaveBeenCalledWith({
        symbol: 'AAPL',
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
