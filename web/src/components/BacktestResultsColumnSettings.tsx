import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import {
  Box,
  Checkbox,
  IconButton,
  Stack,
  Typography,
} from '@mui/material'

import {
  BACKTEST_RESULTS_COLUMN_IDS,
  BACKTEST_RESULTS_COLUMN_LABELS,
  DEFAULT_BACKTEST_RESULTS_TABLE_COLUMNS,
  type BacktestResultsColumnId,
} from '../backtests/resultsTableColumns'

interface BacktestResultsColumnSettingsProps {
  visibleColumns: string[]
  onChange: (next: BacktestResultsColumnId[]) => void
}

function buildEditorRows(visibleColumns: string[]): BacktestResultsColumnId[] {
  const visibleSet = new Set(visibleColumns)
  const orderedVisible = visibleColumns.filter((columnId): columnId is BacktestResultsColumnId =>
    BACKTEST_RESULTS_COLUMN_IDS.includes(columnId as BacktestResultsColumnId),
  )
  const hidden = BACKTEST_RESULTS_COLUMN_IDS.filter((columnId) => !visibleSet.has(columnId))
  return [...orderedVisible, ...hidden]
}

export function BacktestResultsColumnSettings({
  visibleColumns,
  onChange,
}: BacktestResultsColumnSettingsProps) {
  const rows = buildEditorRows(visibleColumns)
  const visibleSet = new Set(visibleColumns)

  const updateVisible = (columnId: BacktestResultsColumnId, checked: boolean) => {
    if (checked) {
      if (visibleSet.has(columnId)) {
        return
      }
      onChange([...visibleColumns.filter((id): id is BacktestResultsColumnId =>
        BACKTEST_RESULTS_COLUMN_IDS.includes(id as BacktestResultsColumnId),
      ), columnId])
      return
    }

    const next = visibleColumns.filter((id) => id !== columnId) as BacktestResultsColumnId[]
    if (next.length === 0) {
      return
    }
    onChange(next)
  }

  const moveColumn = (columnId: BacktestResultsColumnId, direction: -1 | 1) => {
    const visibleOnly = visibleColumns.filter((id): id is BacktestResultsColumnId =>
      BACKTEST_RESULTS_COLUMN_IDS.includes(id as BacktestResultsColumnId),
    )
    const index = visibleOnly.indexOf(columnId)
    if (index === -1) {
      return
    }
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= visibleOnly.length) {
      return
    }
    const next = [...visibleOnly]
    const [removed] = next.splice(index, 1)
    next.splice(targetIndex, 0, removed)
    onChange(next)
  }

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Results table columns
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Choose which columns appear on the Backtest Results page and their order.
        </Typography>
      </Box>
      <Stack spacing={0.5}>
        {rows.map((columnId) => {
          const isVisible = visibleSet.has(columnId)
          const visibleOnly = visibleColumns.filter((id): id is BacktestResultsColumnId =>
            BACKTEST_RESULTS_COLUMN_IDS.includes(id as BacktestResultsColumnId),
          )
          const visibleIndex = visibleOnly.indexOf(columnId)

          return (
            <Stack
              key={columnId}
              direction="row"
              spacing={1}
              sx={{
                alignItems: 'center',
                px: 1,
                py: 0.5,
                borderRadius: 1,
                bgcolor: isVisible ? 'action.hover' : 'transparent',
              }}
            >
              <Checkbox
                checked={isVisible}
                onChange={(_event, checked) => updateVisible(columnId, checked)}
                size="small"
              />
              <Typography sx={{ flex: 1 }}>{BACKTEST_RESULTS_COLUMN_LABELS[columnId]}</Typography>
              {isVisible && (
                <Stack direction="row" spacing={0.25}>
                  <IconButton
                    aria-label={`Move ${BACKTEST_RESULTS_COLUMN_LABELS[columnId]} up`}
                    size="small"
                    disabled={visibleIndex <= 0}
                    onClick={() => moveColumn(columnId, -1)}
                  >
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    aria-label={`Move ${BACKTEST_RESULTS_COLUMN_LABELS[columnId]} down`}
                    size="small"
                    disabled={visibleIndex === visibleOnly.length - 1}
                    onClick={() => moveColumn(columnId, 1)}
                  >
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton>
                </Stack>
              )}
            </Stack>
          )
        })}
      </Stack>
      <Typography variant="caption" color="text.secondary">
        At least one column must remain visible. Defaults:{' '}
        {DEFAULT_BACKTEST_RESULTS_TABLE_COLUMNS.map((id) => BACKTEST_RESULTS_COLUMN_LABELS[id]).join(', ')}.
      </Typography>
    </Stack>
  )
}
