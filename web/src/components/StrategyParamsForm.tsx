import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Button,
  IconButton,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import { fetchStrategies } from '../api/strategies'
import type { Resolution } from '../types/marketData'
import type { StrategyMetadata, StrategyParameterMetadata } from '../types/strategies'
import { buildStrategyParams } from '../utils/strategyPresets'
import { parseParamValue } from '../utils/strategyParams'

export interface StrategySelection {
  strategy: string
  strategyParams: Record<string, unknown>
}

interface StrategyParamsFormProps {
  disabled?: boolean
  resolution?: Resolution
  initialSelection?: StrategySelection | null
  showDocumentationButton?: boolean
  onChange: (selection: StrategySelection) => void
}

export function StrategyParamsForm({
  disabled = false,
  resolution = '1d',
  initialSelection = null,
  showDocumentationButton = false,
  onChange,
}: StrategyParamsFormProps) {
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState('')
  const [params, setParams] = useState<Record<string, unknown>>({})
  const [paramsExpanded, setParamsExpanded] = useState(false)
  const [docsOpen, setDocsOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchStrategies()
      .then((items) => {
        if (cancelled) {
          return
        }
        setStrategies(items)
        if (initialSelection) {
          setSelectedName(initialSelection.strategy)
          setParams(initialSelection.strategyParams)
        } else if (items.length > 0) {
          const first = items[0]
          setSelectedName(first.name)
          setParams(buildStrategyParams(first, resolution))
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load strategies')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [initialSelection, resolution])

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.name === selectedName) ?? null,
    [strategies, selectedName],
  )

  useEffect(() => {
    if (!selectedStrategy || initialSelection) {
      return
    }
    setParams(buildStrategyParams(selectedStrategy, resolution))
  }, [resolution, selectedStrategy, initialSelection])

  const paramCount = selectedStrategy ? Object.keys(selectedStrategy.parameters).length : 0
  const documentation = selectedStrategy?.documentation ?? selectedStrategy?.description ?? ''

  useEffect(() => {
    if (!selectedName) {
      return
    }
    onChange({ strategy: selectedName, strategyParams: params })
  }, [selectedName, params, onChange])

  const handleStrategyChange = (name: string) => {
    const strategy = strategies.find((item) => item.name === name) ?? null
    setSelectedName(name)
    setParams(buildStrategyParams(strategy, resolution))
    setParamsExpanded(false)
    setDocsOpen(false)
  }

  const formatDefaultValue = (value: unknown): string => {
    if (value === null || value === undefined) {
      return '—'
    }
    if (typeof value === 'string') {
      return value
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value)
    }
    return JSON.stringify(value)
  }

  const handleParamChange = (name: string, meta: StrategyParameterMetadata, value: unknown) => {
    setParams((current) => ({
      ...current,
      [name]: meta.type === 'boolean' ? value : parseParamValue(meta, String(value)),
    }))
  }

  if (loading) {
    return (
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <CircularProgress size={20} />
        <Typography color="text.secondary">Loading strategies…</Typography>
      </Stack>
    )
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>
  }

  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: showDocumentationButton && selectedStrategy ? '1fr auto' : '1fr' },
          gap: 1,
          alignItems: 'start',
        }}
      >
        <FormControl size="small" fullWidth disabled={disabled}>
          <InputLabel id="strategy-label">Strategy</InputLabel>
          <Select
            labelId="strategy-label"
            label="Strategy"
            value={selectedName}
            onChange={(event) => handleStrategyChange(event.target.value)}
          >
            {strategies.map((strategy) => (
              <MenuItem key={strategy.name} value={strategy.name}>
                {strategy.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {showDocumentationButton && selectedStrategy && (
          <Tooltip title="Open strategy documentation">
            <span>
              <IconButton
                aria-label={`Open documentation for ${selectedStrategy.name}`}
                size="small"
                onClick={() => setDocsOpen(true)}
                disabled={disabled}
                sx={{
                  mt: 0.25,
                  alignSelf: 'center',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  bgcolor: 'background.paper',
                }}
              >
                <InfoOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Box>
      {selectedStrategy && (
        <Typography variant="body2" color="text.secondary">
          {selectedStrategy.description}
        </Typography>
      )}
      {selectedStrategy && paramCount > 0 && (
        <Accordion
          expanded={paramsExpanded}
          onChange={(_, expanded) => setParamsExpanded(expanded)}
          disableGutters
          sx={{
            bgcolor: 'transparent',
            boxShadow: 'none',
            '&::before': { display: 'none' },
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
          }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 44 }}>
            <Typography variant="body2">
              Parameters ({paramCount})
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
                gap: 2,
              }}
            >
              {Object.entries(selectedStrategy.parameters).map(([name, meta]) => {
                const value = params[name]
                if (meta.type === 'boolean') {
                  return (
                    <FormControlLabel
                      key={name}
                      control={
                        <Switch
                          checked={Boolean(value)}
                          onChange={(event) => handleParamChange(name, meta, event.target.checked)}
                          disabled={disabled}
                        />
                      }
                      label={name}
                    />
                  )
                }
                return (
                  <TextField
                    key={name}
                    label={name}
                    size="small"
                    fullWidth
                    type={meta.type === 'string' ? 'text' : 'number'}
                    value={value ?? ''}
                    onChange={(event) => handleParamChange(name, meta, event.target.value)}
                    required={meta.required}
                    disabled={disabled}
                    slotProps={{
                      htmlInput: {
                        min: meta.minimum ?? undefined,
                        max: meta.maximum ?? undefined,
                        step: meta.type === 'integer' ? 1 : 'any',
                      },
                    }}
                  />
                )
              })}
            </Box>
          </AccordionDetails>
        </Accordion>
      )}
      <Typography variant="caption" color="text.secondary">
        Trade markers appear at bar close times.
      </Typography>

      <Dialog
        open={docsOpen && Boolean(selectedStrategy)}
        onClose={() => setDocsOpen(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{ pb: 1 }}>
          {selectedStrategy?.name} documentation
        </DialogTitle>
        <DialogContent dividers>
          {selectedStrategy && (
            <Stack spacing={3}>
              <Box>
                <Typography variant="overline" color="text.secondary">
                  Overview
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {selectedStrategy.description}
                </Typography>
              </Box>
              <Box>
                <Typography variant="overline" color="text.secondary">
                  How it works
                </Typography>
                <Stack spacing={1.5} sx={{ mt: 0.75 }}>
                  {documentation.split('\n\n').map((paragraph) => (
                    <Typography key={paragraph} variant="body2" sx={{ whiteSpace: 'pre-line' }}>
                      {paragraph}
                    </Typography>
                  ))}
                </Stack>
              </Box>
              {paramCount > 0 && (
                <Box>
                  <Typography variant="overline" color="text.secondary">
                    Parameters
                  </Typography>
                  <Table size="small" sx={{ mt: 1 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Parameter</TableCell>
                        <TableCell>Details</TableCell>
                        <TableCell align="right">Default</TableCell>
                        <TableCell align="center">Required</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(selectedStrategy.parameters).map(([name, meta]) => (
                        <TableRow key={name}>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>
                            <Stack spacing={0.25}>
                              <Typography variant="body2" component="span" sx={{ fontFamily: 'monospace' }}>
                                {name}
                              </Typography>
                              {meta.title && (
                                <Typography variant="caption" color="text.secondary">
                                  {meta.title}
                                </Typography>
                              )}
                            </Stack>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" color="text.secondary">
                              {meta.description ?? 'No additional description provided.'}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">{formatDefaultValue(meta.default)}</Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Typography variant="body2">{meta.required ? 'Yes' : 'No'}</Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDocsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
