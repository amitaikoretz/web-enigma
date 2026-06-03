import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, within } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it } from 'vitest'

import { SortableTradeRecordsTable } from './SortableTradeRecordsTable'

describe('SortableTradeRecordsTable', () => {
  it('sorts rows when the user clicks a column header', () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <SortableTradeRecordsTable
          rows={[
            { symbol: 'A', size: 10 },
            { symbol: 'B', size: -5 },
            { symbol: 'C', size: 20 },
          ]}
          getRowKey={(row) => row.symbol}
          defaultSortKey="symbol"
          defaultSortDirection="asc"
          columns={[
            {
              id: 'symbol',
              label: 'Symbol',
              sortValue: (row) => row.symbol,
              render: (row) => row.symbol,
            },
            {
              id: 'size',
              label: 'Size',
              align: 'right',
              defaultSortDirection: 'desc',
              sortValue: (row) => row.size,
              render: (row) => String(row.size),
            },
          ]}
        />
      </ThemeProvider>,
    )

    const table = screen.getByRole('table')

    expect(
      within(table)
        .getAllByRole('row')
        .slice(1)
        .map((row) => within(row).getAllByRole('cell')[0].textContent),
    ).toEqual(['A', 'B', 'C'])

    fireEvent.click(screen.getByRole('button', { name: /size/i }))

    expect(
      within(table)
        .getAllByRole('row')
        .slice(1)
        .map((row) => within(row).getAllByRole('cell')[0].textContent),
    ).toEqual(['C', 'A', 'B'])

    fireEvent.click(screen.getByRole('button', { name: /size/i }))

    expect(
      within(table)
        .getAllByRole('row')
        .slice(1)
        .map((row) => within(row).getAllByRole('cell')[0].textContent),
    ).toEqual(['B', 'A', 'C'])
  })
})
