import { Table, TableBody, TableCell, TableHead, TableRow, TableSortLabel, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'

export type SortDirection = 'asc' | 'desc'
export type SortValue = string | number | null | undefined

export interface SortableTableColumn<T> {
  id: string
  label: string
  align?: 'left' | 'right'
  defaultSortDirection?: SortDirection
  sortValue: (row: T) => SortValue
  render: (row: T, index: number) => ReactNode
}

interface SortableTradeRecordsTableProps<T> {
  rows: T[]
  columns: SortableTableColumn<T>[]
  getRowKey: (row: T, index: number) => string
  defaultSortKey?: string
  defaultSortDirection?: SortDirection
  emptyMessage?: string
}

export function compareSortValues(left: SortValue, right: SortValue, direction: SortDirection): number {
  const factor = direction === 'asc' ? 1 : -1

  if (left === right) {
    return 0
  }
  if (left === null || left === undefined) {
    return 1
  }
  if (right === null || right === undefined) {
    return -1
  }
  if (typeof left === 'string' || typeof right === 'string') {
    return String(left).localeCompare(String(right)) * factor
  }
  return (left - right) * factor
}

export function sortRows<T>(
  rows: T[],
  columns: SortableTableColumn<T>[],
  sortKey: string,
  sortDirection: SortDirection,
): T[] {
  const indexedRows = rows.map((row, index) => ({
    row,
    index,
    sortValue: columns.find((column) => column.id === sortKey)?.sortValue(row),
  }))

  return indexedRows
    .sort((left, right) => {
      const comparison = compareSortValues(left.sortValue, right.sortValue, sortDirection)
      if (comparison !== 0) {
        return comparison
      }
      return left.index - right.index
    })
    .map(({ row }) => row)
}

export function SortableTradeRecordsTable<T>({
  rows,
  columns,
  getRowKey,
  defaultSortKey,
  defaultSortDirection,
  emptyMessage = 'No trade records were emitted.',
}: SortableTradeRecordsTableProps<T>) {
  const initialSortKey = defaultSortKey ?? columns[0]?.id ?? ''
  const initialSortDirection =
    defaultSortDirection ?? columns.find((column) => column.id === initialSortKey)?.defaultSortDirection ?? 'asc'
  const [sortKey, setSortKey] = useState(initialSortKey)
  const [sortDirection, setSortDirection] = useState<SortDirection>(initialSortDirection)

  const sortedRows = useMemo(
    () => sortRows(rows, columns, sortKey, sortDirection),
    [columns, rows, sortDirection, sortKey],
  )

  const handleSort = (column: SortableTableColumn<T>) => {
    if (sortKey === column.id) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }

    setSortKey(column.id)
    setSortDirection(column.defaultSortDirection ?? 'asc')
  }

  if (rows.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        {emptyMessage}
      </Typography>
    )
  }

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          {columns.map((column) => {
            const active = sortKey === column.id
            return (
              <TableCell
                key={column.id}
                align={column.align}
                sortDirection={active ? sortDirection : false}
              >
                <TableSortLabel
                  active={active}
                  direction={active ? sortDirection : column.defaultSortDirection ?? 'asc'}
                  onClick={() => handleSort(column)}
                >
                  {column.label}
                </TableSortLabel>
              </TableCell>
            )
          })}
        </TableRow>
      </TableHead>
      <TableBody>
        {sortedRows.map((row, index) => (
          <TableRow key={getRowKey(row, index)} hover>
            {columns.map((column) => (
              <TableCell key={column.id} align={column.align}>
                {column.render(row, index)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
