import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
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
  onChange: (selection: StrategySelection) => void
}

export function StrategyParamsForm({
  disabled = false,
  resolution = '1d',
  onChange,
}: StrategyParamsFormProps) {
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState('')
  const [params, setParams] = useState<Record<string, unknown>>({})
  const [paramsExpanded, setParamsExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchStrategies()
      .then((items) => {
        if (cancelled) {
          return
        }
        setStrategies(items)
        if (items.length > 0) {
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
  }, [])

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.name === selectedName) ?? null,
    [strategies, selectedName],
  )

  useEffect(() => {
    if (!selectedStrategy) {
      return
    }
    setParams(buildStrategyParams(selectedStrategy, resolution))
  }, [resolution, selectedStrategy])

  const paramCount = selectedStrategy ? Object.keys(selectedStrategy.parameters).length : 0

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
    </Stack>
  )
}
