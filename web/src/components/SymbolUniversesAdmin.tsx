import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { useEffect, useMemo, useState } from 'react'
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined'
import AddIcon from '@mui/icons-material/Add'

import {
  fetchUniverses,
  fetchUniverseConstituents,
  createUserUniverse,
  deleteUserUniverse,
  patchUserUniverse,
  replaceUserUniverseSymbols,
  patchUniverse,
  refreshAllUniverses,
  refreshUniverse,
  syncUniverseRegistry,
} from '../api/universes'
import type { SymbolUniverse } from '../types/universes'

function safeParseJson(value: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  try {
    const parsed = JSON.parse(value) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: 'provider_ref must be a JSON object' }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Invalid JSON' }
  }
}

export function SymbolUniversesAdmin() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [items, setItems] = useState<SymbolUniverse[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const selected = useMemo(
    () => items.find((item) => item.key === selectedKey) ?? null,
    [items, selectedKey],
  )

  const [editDraft, setEditDraft] = useState({
    name: '',
    description: '',
    providerRefText: '{}',
    isActive: true,
    symbolsText: '',
  })

  const [constituentSymbols, setConstituentSymbols] = useState<string[]>([])
  const [loadingConstituents, setLoadingConstituents] = useState(false)

  const [userCreateDraft, setUserCreateDraft] = useState({
    name: '',
    description: '',
    symbolsText: '',
    isActive: true,
  })

  const reload = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const next = await fetchUniverses(false)
      setItems(next)
      if (selectedKey && !next.some((item) => item.key === selectedKey)) {
        setSelectedKey(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load universes')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) {
      setConstituentSymbols([])
      return
    }

    setEditDraft((prev) => ({
      ...prev,
      name: selected.name,
      description: selected.description ?? '',
      providerRefText: JSON.stringify(selected.provider_ref ?? {}, null, 2),
      isActive: selected.is_active,
      symbolsText: selected.kind === 'user' ? prev.symbolsText : '',
    }))

    const today = new Date().toISOString().slice(0, 10)
    setLoadingConstituents(true)
    void fetchUniverseConstituents(selected.key, today)
      .then((result) => {
        setConstituentSymbols(result.symbols)
        if (selected.kind === 'user') {
          setEditDraft((prev) => ({ ...prev, symbolsText: result.symbols.join('\n') }))
        }
      })
      .catch((err) => {
        setConstituentSymbols([])
        setError(err instanceof Error ? err.message : 'Failed to load universe constituents')
      })
      .finally(() => {
        setLoadingConstituents(false)
      })
  }, [selected])

  const handleSyncRegistry = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await syncUniverseRegistry()
      setSuccess(`Submitted registry sync workflow: ${result.workflow_name} (ns=${result.namespace})`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync registry')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveSelected = async () => {
    if (!selected) {
      return
    }
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      if (selected.kind === 'user') {
        await patchUserUniverse(selected.key, {
          name: editDraft.name,
          description: editDraft.description.trim() ? editDraft.description : null,
          is_active: editDraft.isActive,
        })
        setSuccess(`Saved user universe ${selected.key}.`)
      } else {
        const parsed = safeParseJson(editDraft.providerRefText)
        if (!parsed.ok) {
          setError(parsed.error)
          return
        }
        await patchUniverse(selected.key, {
          provider_ref: parsed.value,
          is_active: editDraft.isActive,
        })
        setSuccess(`Saved ${selected.key}.`)
      }
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update universe')
    } finally {
      setLoading(false)
    }
  }

  const parseSymbolsText = (value: string): string[] => {
    return value
      .split(/[,\n]/g)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean)
      .filter((item, idx, arr) => arr.indexOf(item) === idx)
  }

  const handleCreateUserUniverse = async () => {
    const symbols = parseSymbolsText(userCreateDraft.symbolsText)
    if (!userCreateDraft.name.trim()) {
      setError('Name is required for a user universe.')
      return
    }
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const created = await createUserUniverse({
        name: userCreateDraft.name,
        description: userCreateDraft.description.trim() ? userCreateDraft.description : null,
        symbols,
        is_active: userCreateDraft.isActive,
      })
      setSuccess(`Created user universe ${created.key}.`)
      setUserCreateDraft({ name: '', description: '', symbolsText: '', isActive: true })
      await reload()
      setSelectedKey(created.key)
      setCreateDialogOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user universe')
    } finally {
      setLoading(false)
    }
  }

  const handleReplaceUserSymbols = async () => {
    if (!selected || selected.kind !== 'user') {
      return
    }
    const symbols = parseSymbolsText(editDraft.symbolsText)
    if (symbols.length === 0) {
      setError('Provide at least one symbol.')
      return
    }
    const today = new Date().toISOString().slice(0, 10)
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await replaceUserUniverseSymbols(selected.key, { symbols, effective_on: today })
      setSuccess(`Updated symbols for ${selected.key} (added=${result.added}, closed=${result.closed}).`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update symbols')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteSelectedUserUniverse = async () => {
    if (!selected || selected.kind !== 'user') return
    if (!deleteConfirmText.trim() || deleteConfirmText.trim().toUpperCase() !== selected.key.toUpperCase()) return
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      await deleteUserUniverse(selected.key)
      setSuccess(`Deleted user universe ${selected.key}.`)
      setDeleteDialogOpen(false)
      setDeleteConfirmText('')
      setSelectedKey(null)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user universe')
    } finally {
      setLoading(false)
    }
  }

  const handleRefreshSelected = async () => {
    if (!selected) {
      return
    }
    const today = new Date().toISOString().slice(0, 10)
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await refreshUniverse(selected.key, today)
      setSuccess(`Submitted refresh workflow for ${selected.key}: ${result.workflow_name} (ns=${result.namespace})`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit refresh')
    } finally {
      setLoading(false)
    }
  }

  const handleRefreshAll = async () => {
    const today = new Date().toISOString().slice(0, 10)
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await refreshAllUniverses(today)
      setSuccess(`Submitted refresh-all workflow: ${result.workflow_name} (ns=${result.namespace})`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit refresh')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack spacing={2.5}>
      {error && <Alert severity="error">{error}</Alert>}
      {success && <Alert severity="success">{success}</Alert>}

      <Dialog
        open={createDialogOpen}
        onClose={loading ? undefined : () => setCreateDialogOpen(false)}
        aria-labelledby="create-universe-title"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(6px)',
              backgroundColor: 'rgba(0, 0, 0, 0.55)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              maxWidth: 620,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="create-universe-title" sx={{ pb: 1 }}>
          Create user universe
        </DialogTitle>
        <DialogContent sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <TextField
              label="Name"
              value={userCreateDraft.name}
              onChange={(e) => setUserCreateDraft((prev) => ({ ...prev, name: e.target.value }))}
              disabled={loading}
              autoFocus
              placeholder="My Tech Basket"
            />
            <TextField
              label="Description"
              value={userCreateDraft.description}
              onChange={(e) => setUserCreateDraft((prev) => ({ ...prev, description: e.target.value }))}
              disabled={loading}
            />
            <TextField
              label="Symbols (comma/newline separated)"
              value={userCreateDraft.symbolsText}
              onChange={(e) => setUserCreateDraft((prev) => ({ ...prev, symbolsText: e.target.value }))}
              multiline
              minRows={6}
              placeholder="AAPL, MSFT, NVDA"
              disabled={loading}
              helperText="Symbols are uppercased and deduped on save."
            />
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Switch
                checked={userCreateDraft.isActive}
                onChange={(_e, checked) => setUserCreateDraft((prev) => ({ ...prev, isActive: checked }))}
                disabled={loading}
              />
              <Typography>Active</Typography>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, gap: 1 }}>
          <Button onClick={() => setCreateDialogOpen(false)} disabled={loading} variant="outlined" color="inherit">
            Cancel
          </Button>
          <Button
            onClick={() => void handleCreateUserUniverse()}
            disabled={loading}
            variant="contained"
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <AddIcon />}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={deleteDialogOpen}
        onClose={loading ? undefined : () => setDeleteDialogOpen(false)}
        aria-labelledby="delete-universe-title"
        aria-describedby="delete-universe-description"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(6px)',
              backgroundColor: 'rgba(0, 0, 0, 0.55)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              maxWidth: 520,
              p: 0.5,
            },
          },
        }}
      >
        <DialogTitle id="delete-universe-title" sx={{ pb: 1 }}>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
            <Box
              sx={(theme) => ({
                display: 'grid',
                placeItems: 'center',
                width: 48,
                height: 48,
                borderRadius: '50%',
                bgcolor: alpha(theme.palette.error.main, 0.14),
                color: 'error.main',
                flexShrink: 0,
              })}
            >
              <WarningAmberOutlinedIcon sx={{ fontSize: 26 }} />
            </Box>
            <Stack spacing={0.5} sx={{ pt: 0.25, minWidth: 0 }}>
              <Typography variant="h6" component="span">
                Collapse this universe?
              </Typography>
              <Typography variant="body2" color="text.secondary">
                This permanently deletes the user universe and its membership history.
              </Typography>
            </Stack>
          </Stack>
        </DialogTitle>

        <DialogContent id="delete-universe-description" sx={{ pt: 0 }}>
          <Stack spacing={1.5}>
            <Box
              sx={(theme) => ({
                borderRadius: 2,
                border: `1px solid ${alpha(theme.palette.error.main, 0.25)}`,
                bgcolor: alpha(theme.palette.error.main, 0.06),
                px: 1.5,
                py: 1.25,
              })}
            >
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Target: <Box component="span" sx={{ fontFamily: 'monospace' }}>{selected?.key ?? '—'}</Box>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                No re-expansion is possible. You’ll need to recreate it from scratch.
              </Typography>
            </Box>

            <TextField
              label="Type the universe key to confirm"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              disabled={loading}
              autoFocus
              placeholder={selected?.key ?? ''}
              helperText={selected ? `Enter ${selected.key} to enable deletion.` : 'Select a universe first.'}
            />
          </Stack>
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1, gap: 1 }}>
          <Button
            onClick={() => {
              setDeleteDialogOpen(false)
              setDeleteConfirmText('')
            }}
            disabled={loading}
            variant="outlined"
            color="inherit"
          >
            Keep universe
          </Button>
          <Button
            onClick={() => void handleDeleteSelectedUserUniverse()}
            disabled={
              loading ||
              !selected ||
              selected.kind !== 'user' ||
              deleteConfirmText.trim().toUpperCase() !== selected.key.toUpperCase()
            }
            variant="contained"
            color="error"
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            Delete universe
          </Button>
        </DialogActions>
      </Dialog>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'stretch' }}>
        <Paper sx={{ p: 2, flex: 1, minWidth: 320 }}>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="h6">Universes (registry-managed)</Typography>
              <Button
                variant="contained"
                size="small"
                startIcon={<AddIcon />}
                onClick={() => setCreateDialogOpen(true)}
                disabled={loading}
              >
                Create
              </Button>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button variant="outlined" onClick={handleSyncRegistry} disabled={loading} sx={{ flex: 1 }}>
                Sync registry to DB (Argo)
              </Button>
              <Button variant="outlined" onClick={handleRefreshAll} disabled={loading} sx={{ flex: 1 }}>
                Refresh all (Argo)
              </Button>
            </Stack>
            <Divider />
            <Stack spacing={1}>
              {items.length === 0 ? (
                <Typography color="text.secondary">No universes yet.</Typography>
              ) : (
                <Stack spacing={0.75}>
                  {items.map((item) => (
                    <Button
                      key={item.key}
                      variant={item.key === selectedKey ? 'contained' : 'outlined'}
                      onClick={() => setSelectedKey(item.key)}
                      disabled={loading}
                      sx={{ justifyContent: 'space-between' }}
                    >
                      <Box sx={{ textAlign: 'left' }}>
                        <Typography sx={{ fontWeight: 600 }}>{item.key}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {item.name} • {item.kind ?? 'registry'} • provider={item.provider ?? '—'} • {item.is_active ? 'active' : 'inactive'}
                        </Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="caption" color="text.secondary">
                          {item.latest_refresh_status ?? 'no refresh'}
                        </Typography>
                      </Box>
                    </Button>
                  ))}
                </Stack>
              )}
            </Stack>
          </Stack>
        </Paper>

        <Paper sx={{ p: 2, flex: 2, minWidth: 0 }}>
          <Stack spacing={1.5}>
            {!selected ? (
              <Stack spacing={0.75}>
                <Typography variant="h6">Universe details</Typography>
                <Typography color="text.secondary">
                  Select a universe on the left to view and edit details.
                </Typography>
              </Stack>
            ) : (
              <>
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1}
                  sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
                >
                  <Box>
                    <Typography variant="h6">{selected.key}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Latest refresh: {selected.latest_refresh_status ?? '—'}{' '}
                      {selected.latest_refresh_as_of ? `as_of=${selected.latest_refresh_as_of}` : ''}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                    <Button variant="outlined" onClick={reload} disabled={loading}>
                      Reload
                    </Button>
                    <Button variant="outlined" onClick={handleRefreshSelected} disabled={loading}>
                      Refresh now (Argo)
                    </Button>
                    <Button variant="contained" onClick={handleSaveSelected} disabled={loading}>
                      Save
                    </Button>
                  </Stack>
                </Stack>
                <TextField
                  label={selected.kind === 'user' ? 'Name' : 'Name (registry)'}
                  value={editDraft.name}
                  onChange={(e) => setEditDraft((prev) => ({ ...prev, name: e.target.value }))}
                  disabled={loading || selected.kind !== 'user'}
                />
                <TextField label="Provider" value={selected.provider ?? '—'} disabled />
                <TextField
                  label={selected.kind === 'user' ? 'Description' : 'Description (registry)'}
                  value={editDraft.description}
                  onChange={(e) => setEditDraft((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={loading || selected.kind !== 'user'}
                />
                <TextField
                  label="Provider ref (JSON)"
                  value={editDraft.providerRefText}
                  onChange={(e) => setEditDraft((prev) => ({ ...prev, providerRefText: e.target.value }))}
                  multiline
                  minRows={6}
                  disabled={loading || selected.kind === 'user'}
                />
                {selected.kind !== 'user' && (
                  <TextField
                    label="Constituents"
                    value={constituentSymbols.join(', ')}
                    multiline
                    minRows={3}
                    disabled
                    helperText={
                      loadingConstituents
                        ? 'Loading constituents…'
                        : constituentSymbols.length === 0
                          ? 'No symbols are available for this universe yet.'
                          : `${constituentSymbols.length} symbols`
                    }
                  />
                )}
                {selected.kind === 'user' && (
                  <Stack spacing={1}>
                    <TextField
                      label="Replace symbols (comma/newline separated)"
                      value={editDraft.symbolsText}
                      onChange={(e) => setEditDraft((prev) => ({ ...prev, symbolsText: e.target.value }))}
                      multiline
                      minRows={4}
                      placeholder="AAPL, MSFT, NVDA"
                      disabled={loading}
                      helperText="This versions membership effective today."
                    />
                    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                      <Button variant="outlined" onClick={handleReplaceUserSymbols} disabled={loading}>
                        Replace symbols (versioned)
                      </Button>
                      <Button
                        color="error"
                        variant="outlined"
                        onClick={() => {
                          setDeleteDialogOpen(true)
                          setDeleteConfirmText('')
                        }}
                        disabled={loading}
                      >
                        Delete universe
                      </Button>
                    </Stack>
                  </Stack>
                )}
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Switch
                    checked={editDraft.isActive}
                    onChange={(_e, checked) => setEditDraft((prev) => ({ ...prev, isActive: checked }))}
                    disabled={loading}
                  />
                  <Typography>Active</Typography>
                </Stack>
              </>
            )}
          </Stack>
        </Paper>
      </Stack>
    </Stack>
  )
}
