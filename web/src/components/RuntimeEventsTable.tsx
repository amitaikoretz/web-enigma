import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Box,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { Fragment, useMemo, useState } from 'react'

import { RuntimeEventSeverityChip } from './RuntimeEventSeverityChip'
import type { LiveRuntimeFilters } from '../api/liveRuntime'
import type { WorkerEvent } from '../types/liveRuntime'
import type { TimeDisplayFormat } from '../types/settings'
import { formatInTimezone } from '../utils/datetime'
import { formatEventType, KNOWN_EVENT_TYPES } from '../utils/runtimeEventLabels'

interface RuntimeEventsTableProps {
  events: WorkerEvent[]
  filters: LiveRuntimeFilters
  workerOptions: string[]
  timezone: string
  timeDisplayFormat: TimeDisplayFormat
  onFiltersChange: (filters: LiveRuntimeFilters) => void
}

const LIMIT_OPTIONS = [50, 100, 200]

export function RuntimeEventsTable({
  events,
  filters,
  workerOptions,
  timezone,
  timeDisplayFormat,
  onFiltersChange,
}: RuntimeEventsTableProps) {
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null)

  const eventTypeOptions = useMemo(() => {
    const fromEvents = new Set(events.map((event) => event.event_type))
    KNOWN_EVENT_TYPES.forEach((eventType) => fromEvents.add(eventType))
    return Array.from(fromEvents).sort()
  }, [events])

  function updateFilter(partial: Partial<LiveRuntimeFilters>) {
    onFiltersChange({ ...filters, ...partial })
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="runtime-worker-filter-label">Worker</InputLabel>
          <Select
            labelId="runtime-worker-filter-label"
            label="Worker"
            value={filters.worker_id ?? ''}
            onChange={(event) =>
              updateFilter({ worker_id: event.target.value || undefined })
            }
          >
            <MenuItem value="">All</MenuItem>
            {workerOptions.map((workerId) => (
              <MenuItem key={workerId} value={workerId}>
                {workerId}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 220 }}>
          <InputLabel id="runtime-event-type-filter-label">Event type</InputLabel>
          <Select
            labelId="runtime-event-type-filter-label"
            label="Event type"
            value={filters.event_type ?? ''}
            onChange={(event) =>
              updateFilter({ event_type: event.target.value || undefined })
            }
          >
            <MenuItem value="">All</MenuItem>
            {eventTypeOptions.map((eventType) => (
              <MenuItem key={eventType} value={eventType}>
                {formatEventType(eventType)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <TextField
          size="small"
          label="Symbol key"
          value={filters.symbol_key ?? ''}
          onChange={(event) =>
            updateFilter({ symbol_key: event.target.value || undefined })
          }
          sx={{ minWidth: 180 }}
        />

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel id="runtime-limit-filter-label">Limit</InputLabel>
          <Select
            labelId="runtime-limit-filter-label"
            label="Limit"
            value={filters.limit ?? 100}
            onChange={(event) =>
              updateFilter({ limit: Number(event.target.value) })
            }
          >
            {LIMIT_OPTIONS.map((limit) => (
              <MenuItem key={limit} value={limit}>
                {limit}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      {events.length === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No events yet. Start the live controller and workers to see activity.
        </Typography>
      ) : (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>Time</TableCell>
                <TableCell>Source</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Symbol</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((event) => {
                const expanded = expandedEventId === event.id
                return (
                  <Fragment key={event.id}>
                    <TableRow hover>
                      <TableCell padding="checkbox">
                        <IconButton
                          size="small"
                          aria-label={expanded ? 'Collapse event details' : 'Expand event details'}
                          onClick={() => setExpandedEventId(expanded ? null : event.id)}
                          sx={{
                            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            transition: 'transform 0.2s',
                          }}
                        >
                          <ExpandMoreIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                      <TableCell>
                        {formatInTimezone(event.created_at, timezone, timeDisplayFormat, true)}
                      </TableCell>
                      <TableCell>{event.worker_id}</TableCell>
                      <TableCell>{formatEventType(event.event_type)}</TableCell>
                      <TableCell>
                        <RuntimeEventSeverityChip severity={event.severity} />
                      </TableCell>
                      <TableCell>{event.symbol_key ?? '—'}</TableCell>
                    </TableRow>
                    {expanded && (
                      <TableRow>
                        <TableCell colSpan={6} sx={{ bgcolor: 'action.hover' }}>
                          <Box
                            component="pre"
                            sx={{
                              m: 0,
                              p: 1.5,
                              overflow: 'auto',
                              fontFamily: 'monospace',
                              fontSize: '0.8rem',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                            }}
                          >
                            {JSON.stringify(event.payload, null, 2)}
                          </Box>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  )
}
