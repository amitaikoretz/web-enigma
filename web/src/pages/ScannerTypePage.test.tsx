import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const fetchScanRunsMock = vi.hoisted(() => vi.fn())
const fetchScanParamsMock = vi.hoisted(() => vi.fn())
const createScanRunMock = vi.hoisted(() => vi.fn())

vi.mock('../api/scans', () => ({
  createScanRun: createScanRunMock,
  fetchScanParams: fetchScanParamsMock,
  fetchScanRuns: fetchScanRunsMock,
}))

import { ScannerTypePage } from './ScannerTypePage'

describe('ScannerTypePage', () => {
  it('opens a modal confirming a successful launch', async () => {
    fetchScanRunsMock.mockResolvedValue({ items: [] })
    fetchScanParamsMock.mockResolvedValue({
      defaults: {},
      schema: null,
    })
    createScanRunMock.mockResolvedValue({
      scan_id: 'scan-1',
      scan_type: 'momentum',
      status: 'running',
      created_at: '2026-06-04T12:00:00.000Z',
      updated_at: '2026-06-04T12:00:00.000Z',
      params: {},
      argo_namespace: 'ns',
      argo_workflow_name: 'wf',
    })

    render(
      <MemoryRouter initialEntries={['/scanners/momentum']}>
        <Routes>
          <Route path="/scanners/:scanType" element={<ScannerTypePage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('No runs yet.')
    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    await waitFor(() =>
      expect(createScanRunMock).toHaveBeenCalledWith('momentum', {
        params: {},
      }),
    )

    expect(await screen.findByText('Scanner launched')).toBeInTheDocument()
    expect(screen.getByText(/launch submitted successfully/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /run scan-1/i })).toHaveAttribute(
      'href',
      '/scanners/momentum/runs/scan-1',
    )
  })

  it('opens a modal reporting a failed launch', async () => {
    fetchScanRunsMock.mockResolvedValue({ items: [] })
    fetchScanParamsMock.mockResolvedValue({
      defaults: {},
      schema: null,
    })
    createScanRunMock.mockRejectedValue(new Error('Argo submit failed'))

    render(
      <MemoryRouter initialEntries={['/scanners/options']}>
        <Routes>
          <Route path="/scanners/:scanType" element={<ScannerTypePage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('No runs yet.')
    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    await waitFor(() =>
      expect(createScanRunMock).toHaveBeenCalledWith('options', {
        params: {},
      }),
    )

    expect(await screen.findByText('Scanner launch failed')).toBeInTheDocument()
    expect(screen.getByText('Argo submit failed')).toBeInTheDocument()
  })
})
