import {
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'

import { CollapsibleSection } from './CollapsibleSection'
import type { RuntimeState } from '../types/liveRuntime'
import type { TimeDisplayFormat } from '../types/settings'
import { formatInTimezone } from '../utils/datetime'
import { isStaleHeartbeat } from '../utils/runtimeEventLabels'

interface RuntimeStatePanelProps {
  state: RuntimeState
  timezone: string
  timeDisplayFormat: TimeDisplayFormat
}

export function RuntimeStatePanel({ state, timezone, timeDisplayFormat }: RuntimeStatePanelProps) {
  const { control_flags: controlFlags } = state
  const pauseCount =
    controlFlags.paused_contracts.length +
    controlFlags.paused_symbols.length +
    controlFlags.paused_shards.length

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Chip label={`Assignment v${state.assignment_version}`} size="small" />
        <Chip
          label={controlFlags.kill_switch_enabled ? 'Kill switch ON' : 'Kill switch off'}
          color={controlFlags.kill_switch_enabled ? 'error' : 'default'}
          size="small"
        />
        {pauseCount > 0 && (
          <Chip label={`${pauseCount} pause${pauseCount === 1 ? '' : 's'} active`} color="warning" size="small" />
        )}
      </Stack>

      <Typography variant="subtitle1">Workers</Typography>
      {state.workers.length === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No worker heartbeats reported.
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Worker</TableCell>
              <TableCell>Pod</TableCell>
              <TableCell>Shard</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Symbols</TableCell>
              <TableCell>Last heartbeat</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {state.workers.map((worker) => {
              const stale = isStaleHeartbeat(worker.updated_at)
              return (
                <TableRow key={worker.worker_id} sx={stale ? { bgcolor: 'warning.light', opacity: 0.9 } : undefined}>
                  <TableCell>{worker.worker_id}</TableCell>
                  <TableCell>{worker.pod_name}</TableCell>
                  <TableCell>{worker.shard_id}</TableCell>
                  <TableCell>{worker.status}</TableCell>
                  <TableCell align="right">{worker.owned_symbol_count}</TableCell>
                  <TableCell>
                    {formatInTimezone(worker.updated_at, timezone, timeDisplayFormat, true)}
                    {stale ? ' (stale)' : ''}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}

      <CollapsibleSection title="Shard assignments" subtitle={`${state.assignments.length} shard(s)`}>
        {state.assignments.length === 0 ? (
          <Typography color="text.secondary" variant="body2">
            No shard assignments published.
          </Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Shard</TableCell>
                <TableCell>Symbol keys</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {state.assignments.map((assignment) => (
                <TableRow key={assignment.shard_id}>
                  <TableCell>{assignment.shard_id}</TableCell>
                  <TableCell>{assignment.symbol_keys.join(', ') || '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Active leases" subtitle={`${state.leases.length} lease(s)`}>
        {state.leases.length === 0 ? (
          <Typography color="text.secondary" variant="body2">
            No active symbol leases.
          </Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Worker</TableCell>
                <TableCell>Shard</TableCell>
                <TableCell>Expires</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {state.leases.map((lease) => (
                <TableRow key={`${lease.symbol_key}-${lease.worker_id}`}>
                  <TableCell>{lease.symbol_key}</TableCell>
                  <TableCell>{lease.worker_id}</TableCell>
                  <TableCell>{lease.shard_id}</TableCell>
                  <TableCell>
                    {formatInTimezone(lease.expires_at, timezone, timeDisplayFormat, true)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      {(controlFlags.paused_contracts.length > 0 ||
        controlFlags.paused_symbols.length > 0 ||
        controlFlags.paused_shards.length > 0) && (
        <CollapsibleSection
          title="Active pauses"
          defaultExpanded
          subtitle={`${pauseCount} scope(s)`}
        >
          <Stack spacing={1}>
            {controlFlags.paused_contracts.length > 0 && (
              <Typography variant="body2">
                Contracts: {controlFlags.paused_contracts.join(', ')}
              </Typography>
            )}
            {controlFlags.paused_symbols.length > 0 && (
              <Typography variant="body2">
                Symbols: {controlFlags.paused_symbols.join(', ')}
              </Typography>
            )}
            {controlFlags.paused_shards.length > 0 && (
              <Typography variant="body2">
                Shards: {controlFlags.paused_shards.join(', ')}
              </Typography>
            )}
          </Stack>
        </CollapsibleSection>
      )}
    </Stack>
  )
}
