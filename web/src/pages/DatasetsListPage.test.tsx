import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const fetchDatasetsMock = vi.hoisted(() => vi.fn())
const deleteDatasetMock = vi.hoisted(() => vi.fn())

vi.mock('../api/datasets', () => ({
  deleteDataset: deleteDatasetMock,
  fetchDatasets: fetchDatasetsMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { DatasetsListPage } from './DatasetsListPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{JSON.stringify({ pathname: location.pathname, state: location.state })}</div>
}

describe('DatasetsListPage', () => {
  beforeEach(() => {
    fetchDatasetsMock.mockResolvedValue({
      items: [
        {
          id: 'ds-1',
          name: 'My dataset',
          symbol: 'AAPL',
          provider: 'alpaca',
          resolution: '5m',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'completed',
          argo_namespace: null,
          argo_workflow_name: null,
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: '/tmp/datasets/aapl.parquet',
          manifest_path: '/tmp/datasets/aapl.manifest.json',
          error_message: null,
          progress_pct: 100,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('deep-links a single selected dataset into the daily-index wizard route with provenance', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <Routes>
          <Route path="/backtests/datasets" element={<DatasetsListPage />} />
          <Route path="/models/daily-index/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('My dataset')
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getByRole('button', { name: /train daily index forecast/i }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/models/daily-index/new')
    expect(screen.getByTestId('location')).toHaveTextContent('"sourceKind":"dataset"')
    expect(screen.getByTestId('location')).toHaveTextContent('"selectedCount":1')
    expect(screen.getByTestId('location')).toHaveTextContent('"symbol":"AAPL"')
  })

  it('disables the daily-index launch when multiple datasets are selected', async () => {
    fetchDatasetsMock.mockResolvedValue({
      items: [
        {
          id: 'ds-1',
          name: 'My dataset',
          symbol: 'AAPL',
          provider: 'alpaca',
          resolution: '5m',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'completed',
          argo_namespace: null,
          argo_workflow_name: null,
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: '/tmp/datasets/aapl.parquet',
          manifest_path: '/tmp/datasets/aapl.manifest.json',
          error_message: null,
          progress_pct: 100,
        },
        {
          id: 'ds-2',
          name: 'Other dataset',
          symbol: 'QQQ',
          provider: 'alpaca',
          resolution: '5m',
          start_date: '2026-05-01',
          end_date: '2026-06-01',
          created_at: '2026-06-07T00:00:00Z',
          updated_at: '2026-06-07T00:00:00Z',
          status: 'completed',
          argo_namespace: null,
          argo_workflow_name: null,
          params_json: {},
          output_dir: '/tmp/datasets',
          dataset_parquet_path: '/tmp/datasets/qqq.parquet',
          manifest_path: '/tmp/datasets/qqq.manifest.json',
          error_message: null,
          progress_pct: 100,
        },
      ],
      total: 2,
      page: 1,
      page_size: 2,
    })

    render(
      <MemoryRouter initialEntries={['/backtests/datasets']}>
        <Routes>
          <Route path="/backtests/datasets" element={<DatasetsListPage />} />
          <Route path="/models/daily-index/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('My dataset')
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getAllByRole('checkbox')[2])
    expect(screen.getByRole('button', { name: /train daily index forecast/i })).toBeDisabled()
  })
})
