import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ModelTrainingLaunchDialog } from './ModelTrainingLaunchDialog'

describe('ModelTrainingLaunchDialog daily index dataset-backed flow', () => {
  it('uses dataset provenance and hides editable universe controls', async () => {
    const onSubmit = vi.fn()

    render(
      <ModelTrainingLaunchDialog
        open
        allowedFamilies={['daily_index_forecast']}
        selectedCount={1}
        selectionLabel="datasets"
        dailyIndexDatasetSource={{ symbol: 'AAPL', start_date: '2026-05-01', end_date: '2026-06-01' }}
        submitting={false}
        error={null}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.queryByLabelText(/start date/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/end date/i)).not.toBeInTheDocument()
    expect(screen.getByText(/uses dataset provenance: aapl from 2026-05-01 to 2026-06-01/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          family: 'daily_index_forecast',
          request: expect.objectContaining({
            universe: expect.objectContaining({
              start_date: '2026-05-01',
              end_date: '2026-06-01',
              symbols: [expect.objectContaining({ symbol: 'AAPL' })],
            }),
          }),
        }),
      ),
    )
  })
})
