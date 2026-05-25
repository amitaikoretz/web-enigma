import AddIcon from '@mui/icons-material/Add'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import ViewListIcon from '@mui/icons-material/ViewList'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { deleteTradingContract, fetchTradingContracts } from '../api/tradingContracts'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ContractCreateForm } from '../components/ContractCreateForm'
import { ContractEditDialog } from '../components/ContractEditDialog'
import { ContractStatusChip } from '../components/ContractStatusChip'
import { useSettings } from '../settings/useSettings'
import type { TradingContract } from '../types/tradingContracts'
import { resolveContractStatus } from '../utils/contractStatus'
import { formatInTimezone } from '../utils/datetime'

type ContractsTab = 'existing' | 'new'

function parseTab(value: string | null): ContractsTab {
  return value === 'new' ? 'new' : 'existing'
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

export function ContractsPage() {
  const { platformSettings, appearance } = useSettings()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<ContractsTab>(() => parseTab(searchParams.get('tab')))
  const [items, setItems] = useState<TradingContract[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [editTarget, setEditTarget] = useState<TradingContract | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TradingContract | null>(null)
  const [deleting, setDeleting] = useState(false)

  const loadContracts = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    try {
      const response = await fetchTradingContracts()
      setItems(response)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trading contracts')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void loadContracts()
  }, [loadContracts])

  useEffect(() => {
    const nextTab = parseTab(searchParams.get('tab'))
    setActiveTab(nextTab)
  }, [searchParams])

  function handleTabChange(nextTab: ContractsTab) {
    setActiveTab(nextTab)
    if (nextTab === 'new') {
      setSearchParams({ tab: 'new' })
      return
    }
    setSearchParams({})
  }

  function handleContractCreated() {
    setSuccessMessage('Contract created.')
    void loadContracts(true)
    handleTabChange('existing')
  }

  function handleContractUpdated() {
    setSuccessMessage('Contract updated. Workers will drop the previous mandate on their next sync.')
    void loadContracts(true)
  }

  async function confirmDelete() {
    if (!deleteTarget) {
      return
    }
    setDeleting(true)
    setError(null)
    try {
      await deleteTradingContract(deleteTarget.id)
      setSuccessMessage(`Deleted contract for ${deleteTarget.symbol}. Workers will release it immediately.`)
      setDeleteTarget(null)
      await loadContracts(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete trading contract')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Contracts</Typography>
        <Typography color="text.secondary">
          Manage
        </Typography>
      </Stack>

      {successMessage && (
        <Alert severity="success" onClose={() => setSuccessMessage(null)}>
          {successMessage}
        </Alert>
      )}

      <Paper sx={{ p: 1.5 }}>
        <Tabs
          value={activeTab}
          onChange={(_event, nextValue: ContractsTab) => handleTabChange(nextValue)}
          variant="scrollable"
          allowScrollButtonsMobile
        >
          <Tab icon={<ViewListIcon />} iconPosition="start" value="existing" label="Existing" />
          <Tab icon={<AddIcon />} iconPosition="start" value="new" label="New" />
        </Tabs>
      </Paper>

      {activeTab === 'existing' && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between' }}>
              <Stack spacing={0.5}>
                <Typography variant="h6">Existing contracts</Typography>
                <Typography color="text.secondary" variant="body2">
                  Active, upcoming, and expired mandates stored in the platform.
                </Typography>
              </Stack>
              <Button
                variant="outlined"
                startIcon={refreshing ? <CircularProgress size={18} /> : <RefreshIcon />}
                onClick={() => void loadContracts(true)}
                disabled={loading || refreshing}
              >
                Refresh
              </Button>
            </Stack>

            {error && <Alert severity="error">{error}</Alert>}

            {loading ? (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', py: 4, justifyContent: 'center' }}>
                <CircularProgress size={24} />
                <Typography color="text.secondary">Loading contracts…</Typography>
              </Stack>
            ) : items.length === 0 ? (
              <Box sx={{ py: 4, textAlign: 'center' }}>
                <Typography color="text.secondary" sx={{ mb: 2 }}>
                  No contracts yet. Create one to get started.
                </Typography>
                <Button variant="contained" onClick={() => handleTabChange('new')}>
                  Create contract
                </Button>
              </Box>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Strategy</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Start</TableCell>
                      <TableCell>End</TableCell>
                      <TableCell align="right">Max trade size</TableCell>
                      <TableCell align="right">Total invested</TableCell>
                      <TableCell>Created</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {items.map((item) => (
                      <TableRow key={item.id} hover>
                        <TableCell>{item.symbol}</TableCell>
                        <TableCell>{item.strategy}</TableCell>
                        <TableCell>
                          <ContractStatusChip status={resolveContractStatus(item)} />
                        </TableCell>
                        <TableCell>
                          {formatInTimezone(
                            item.start_datetime,
                            platformSettings.platform_behavior.timezone,
                            appearance.time_display_format,
                          )}
                        </TableCell>
                        <TableCell>
                          {formatInTimezone(
                            item.end_datetime,
                            platformSettings.platform_behavior.timezone,
                            appearance.time_display_format,
                          )}
                        </TableCell>
                        <TableCell align="right">{formatCurrency(item.maximum_trade_size)}</TableCell>
                        <TableCell align="right">{formatCurrency(item.total_invested)}</TableCell>
                        <TableCell>
                          {formatInTimezone(
                            item.created_at,
                            platformSettings.platform_behavior.timezone,
                            appearance.time_display_format,
                          )}
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                            <Tooltip title="Edit contract">
                              <IconButton size="small" onClick={() => setEditTarget(item)}>
                                <EditOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Delete contract">
                              <IconButton size="small" color="error" onClick={() => setDeleteTarget(item)}>
                                <DeleteOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Stack>
        </Paper>
      )}

      {activeTab === 'new' && <ContractCreateForm onCreated={handleContractCreated} />}

      <ContractEditDialog
        contract={editTarget}
        open={editTarget !== null}
        onClose={() => setEditTarget(null)}
        onUpdated={handleContractUpdated}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete contract?"
        description={
          deleteTarget
            ? `Delete the ${deleteTarget.symbol} / ${deleteTarget.strategy} mandate? Live workers will revoke and release this contract on their next sync.`
            : ''
        }
        confirmLabel="Delete contract"
        loading={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </Stack>
  )
}
