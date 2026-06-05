import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Autocomplete,
  Box,
  CircularProgress,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import { fetchReturnForecastModels } from '../api/returnForecastModels'
import { fetchRiskModels } from '../api/riskModels'
import type { BacktestModelPolicyInput } from '../types/backtests'
import type { ReturnForecastModelListItem } from '../types/returnForecastModels'
import type { RiskModelListItem } from '../types/riskModels'

interface BacktestModelPolicyFormProps {
  disabled?: boolean
  initialValue?: BacktestModelPolicyInput | null
  onChange: (value: BacktestModelPolicyInput | null) => void
}

function formatModelSummary(item: { targets?: string[]; status?: string; targets_total?: number; targets_done?: number }): string {
  const parts: string[] = []
  if (Array.isArray(item.targets) && item.targets.length > 0) {
    parts.push(item.targets.join(', '))
  }
  if (typeof item.targets_done === 'number' && typeof item.targets_total === 'number') {
    parts.push(`${item.targets_done}/${item.targets_total} targets`)
  }
  if (typeof item.status === 'string' && item.status) {
    parts.push(item.status)
  }
  return parts.join(' · ')
}

function buildModelOptions(items: Array<ReturnForecastModelListItem | RiskModelListItem>, initialId: string): string[] {
  const ids = items
    .filter((item) => item.status === 'succeeded')
    .map((item) => item.group_id)
  if (initialId && !ids.includes(initialId)) {
    ids.unshift(initialId)
  }
  return ids
}

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function BacktestModelPolicyForm({
  disabled = false,
  initialValue = null,
  onChange,
}: BacktestModelPolicyFormProps) {
  const [forecastModels, setForecastModels] = useState<ReturnForecastModelListItem[]>([])
  const [riskModels, setRiskModels] = useState<RiskModelListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(Boolean(initialValue))
  const [forecastModelId, setForecastModelId] = useState(
    initialValue?.forecast_model?.group_id ?? initialValue?.forecast_model?.model_artifact_path ?? '',
  )
  const [riskModelId, setRiskModelId] = useState(
    initialValue?.risk_model?.group_id ?? initialValue?.risk_model?.model_artifact_path ?? '',
  )
  const [thresholdBps, setThresholdBps] = useState(String(initialValue?.threshold_bps ?? 1.0))
  const [targetEdgeBps, setTargetEdgeBps] = useState(String(initialValue?.target_edge_bps ?? 5.0))
  const [maxRiskFraction, setMaxRiskFraction] = useState(String(initialValue?.max_risk_fraction ?? 0.001))
  const [minSignalScore, setMinSignalScore] = useState(String(initialValue?.min_signal_score ?? 0.0))
  const [allowShort, setAllowShort] = useState(Boolean(initialValue?.allow_short ?? false))

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([fetchReturnForecastModels(), fetchRiskModels()])
      .then(([forecast, risk]) => {
        if (cancelled) {
          return
        }
        setForecastModels(forecast)
        setRiskModels(risk)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load models')
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

  useEffect(() => {
    setForecastModelId(initialValue?.forecast_model?.group_id ?? initialValue?.forecast_model?.model_artifact_path ?? '')
    setRiskModelId(initialValue?.risk_model?.group_id ?? initialValue?.risk_model?.model_artifact_path ?? '')
    setThresholdBps(String(initialValue?.threshold_bps ?? 1.0))
    setTargetEdgeBps(String(initialValue?.target_edge_bps ?? 5.0))
    setMaxRiskFraction(String(initialValue?.max_risk_fraction ?? 0.001))
    setMinSignalScore(String(initialValue?.min_signal_score ?? 0.0))
    setAllowShort(Boolean(initialValue?.allow_short ?? false))
    setExpanded(Boolean(initialValue))
  }, [initialValue])

  const forecastOptions = useMemo(
    () => buildModelOptions(forecastModels, forecastModelId),
    [forecastModels, forecastModelId],
  )
  const riskOptions = useMemo(() => buildModelOptions(riskModels, riskModelId), [riskModels, riskModelId])
  const forecastSummaryMap = useMemo(
    () => new Map(forecastModels.map((item) => [item.group_id, formatModelSummary(item)])),
    [forecastModels],
  )
  const riskSummaryMap = useMemo(
    () => new Map(riskModels.map((item) => [item.group_id, formatModelSummary(item)])),
    [riskModels],
  )

  useEffect(() => {
    const hasModel = Boolean(forecastModelId.trim() || riskModelId.trim())
    if (!hasModel) {
      onChange(null)
      return
    }
    onChange({
      ...(forecastModelId.trim()
        ? { forecast_model: { group_id: forecastModelId.trim() } }
        : {}),
      ...(riskModelId.trim() ? { risk_model: { group_id: riskModelId.trim() } } : {}),
      threshold_bps: parseNumber(thresholdBps, 1.0),
      target_edge_bps: parseNumber(targetEdgeBps, 5.0),
      max_risk_fraction: parseNumber(maxRiskFraction, 0.001),
      min_signal_score: parseNumber(minSignalScore, 0.0),
      allow_short: allowShort,
    })
  }, [allowShort, forecastModelId, maxRiskFraction, minSignalScore, onChange, riskModelId, targetEdgeBps, thresholdBps])

  if (loading) {
    return (
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <CircularProgress size={20} />
        <Typography color="text.secondary">Loading model policy options…</Typography>
      </Stack>
    )
  }

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
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
        <Typography variant="body2">Model policy</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Stack spacing={2}>
          {error && <Alert severity="warning">{error}</Alert>}
          <Typography variant="body2" color="text.secondary">
            Leave both model selectors empty for a trigger-only backtest. Pick one model family or both if you want
            the backtest to gate or size entries using model scores.
          </Typography>
          <Autocomplete
            freeSolo
            disabled={disabled}
            options={forecastOptions}
            value={forecastModelId}
            onInputChange={(_, value) => setForecastModelId(value)}
            onChange={(_, value) => setForecastModelId(value ?? '')}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Forecast model group"
                size="small"
                helperText={forecastModelId && forecastSummaryMap.get(forecastModelId) ? forecastSummaryMap.get(forecastModelId) : 'Optional. Uses the return forecast model group id.'}
              />
            )}
          />
          <Autocomplete
            freeSolo
            disabled={disabled}
            options={riskOptions}
            value={riskModelId}
            onInputChange={(_, value) => setRiskModelId(value)}
            onChange={(_, value) => setRiskModelId(value ?? '')}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Risk model group"
                size="small"
                helperText={riskModelId && riskSummaryMap.get(riskModelId) ? riskSummaryMap.get(riskModelId) : 'Optional. Uses the risk model group id.'}
              />
            )}
          />
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
              gap: 2,
            }}
          >
            <TextField
              label="Threshold bps"
              type="number"
              size="small"
              value={thresholdBps}
              onChange={(event) => setThresholdBps(event.target.value)}
              disabled={disabled}
              helperText="Minimum edge required after costs."
              slotProps={{ htmlInput: { min: 0, step: 0.1 } }}
            />
            <TextField
              label="Target edge bps"
              type="number"
              size="small"
              value={targetEdgeBps}
              onChange={(event) => setTargetEdgeBps(event.target.value)}
              disabled={disabled}
              helperText="Scales position size as edge increases."
              slotProps={{ htmlInput: { min: 0, step: 0.1 } }}
            />
            <TextField
              label="Max risk fraction"
              type="number"
              size="small"
              value={maxRiskFraction}
              onChange={(event) => setMaxRiskFraction(event.target.value)}
              disabled={disabled}
              helperText="Fraction of capital allowed at risk."
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.0001 } }}
            />
            <TextField
              label="Min signal score"
              type="number"
              size="small"
              value={minSignalScore}
              onChange={(event) => setMinSignalScore(event.target.value)}
              disabled={disabled}
              helperText="Optional floor for weak model signals."
              slotProps={{ htmlInput: { step: 0.01 } }}
            />
          </Box>
          <FormControlLabel
            control={
              <Switch
                checked={allowShort}
                onChange={(_event, checked) => setAllowShort(checked)}
                disabled={disabled}
              />
            }
            label="Allow short signals"
          />
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
