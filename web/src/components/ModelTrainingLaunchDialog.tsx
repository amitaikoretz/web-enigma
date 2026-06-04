import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import type { RiskModelCreateRequest } from '../types/riskModels'
import type { ReturnForecastModelCreateRequest } from '../types/returnForecastModels'

export type ModelTrainingFamily = 'risk' | 'return_forecast'

export type ModelTrainingLaunchPayload = {
  family: ModelTrainingFamily
  request: RiskModelCreateRequest | ReturnForecastModelCreateRequest
}

interface ModelTrainingLaunchDialogProps {
  open: boolean
  family: ModelTrainingFamily
  selectedBacktestCount: number
  submitting: boolean
  error: string | null
  onClose: () => void
  onSubmit: (payload: ModelTrainingLaunchPayload) => void
}

function buildDefaultRequest(family: ModelTrainingFamily): RiskModelCreateRequest | ReturnForecastModelCreateRequest {
  if (family === 'risk') {
    return {
      backtest_ids: [],
      targets: [
        { target_key: 'stop_prob', task_type: 'classification' },
        { target_key: 'mae', task_type: 'regression' },
      ],
      dataset_config: {},
      train_config: { random_seed: 7 },
    }
  }

  return {
    backtest_ids: [],
    targets: [{ target_key: 'forecast_return', task_type: 'regression' }],
    dataset_config: {},
    train_config: {
      random_seed: 7,
      lookback_bars: 60,
      horizon_bars: 5,
      allow_short: true,
    },
  }
}

export function ModelTrainingLaunchDialog({
  open,
  family,
  selectedBacktestCount,
  submitting,
  error,
  onClose,
  onSubmit,
}: ModelTrainingLaunchDialogProps) {
  const [randomSeed, setRandomSeed] = useState('7')
  const [lookbackBars, setLookbackBars] = useState('60')
  const [horizonBars, setHorizonBars] = useState('5')
  const [allowShort, setAllowShort] = useState(true)

  const familyLabel = useMemo(
    () => (family === 'risk' ? 'Risk model' : 'Return forecast model'),
    [family],
  )

  useEffect(() => {
    if (!open) {
      return
    }
    const defaults = buildDefaultRequest(family)
    setRandomSeed(String(defaults.train_config.random_seed ?? 7))
    if (family === 'return_forecast') {
      setLookbackBars(String(defaults.train_config.lookback_bars ?? 60))
      setHorizonBars(String(defaults.train_config.horizon_bars ?? 5))
      setAllowShort(Boolean(defaults.train_config.allow_short ?? true))
    }
  }, [family, open])

  function handleSubmit() {
    const baseRequest = buildDefaultRequest(family)
    const request =
      family === 'risk'
        ? {
            ...baseRequest,
            train_config: {
              ...baseRequest.train_config,
              random_seed: Number(randomSeed) || 7,
            },
          }
        : {
            ...baseRequest,
            train_config: {
              ...baseRequest.train_config,
              random_seed: Number(randomSeed) || 7,
              lookback_bars: Number(lookbackBars) || 60,
              horizon_bars: Number(horizonBars) || 5,
              allow_short: allowShort,
            },
          }

    onSubmit({ family, request })
  }

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Train {familyLabel.toLowerCase()}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <Typography color="text.secondary">
            {family === 'risk'
              ? 'Trains stop probability + MAE models from the selected backtests via Argo.'
              : 'Trains a short-horizon return forecast model from the selected backtests via Argo.'}
          </Typography>
          <Typography>
            Selected backtests on this page: <b>{selectedBacktestCount}</b>
          </Typography>
          <TextField
            label="Random seed"
            value={randomSeed}
            onChange={(e) => setRandomSeed(e.target.value)}
            size="small"
            helperText="Used for walk-forward fold configuration in v1."
          />
          {family === 'return_forecast' && (
            <>
              <TextField
                label="Lookback bars"
                value={lookbackBars}
                onChange={(e) => setLookbackBars(e.target.value)}
                size="small"
                helperText="How many bars to use as model context."
              />
              <TextField
                label="Horizon bars"
                value={horizonBars}
                onChange={(e) => setHorizonBars(e.target.value)}
                size="small"
                helperText="How many bars ahead to forecast."
              />
              <FormControlLabel
                control={<Checkbox checked={allowShort} onChange={(e) => setAllowShort(e.target.checked)} />}
                label="Allow short signals"
              />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          onClick={() => handleSubmit()}
          variant="contained"
          disabled={submitting || selectedBacktestCount === 0}
        >
          {submitting ? 'Submitting…' : 'Start training'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
