import { useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'

import { createReturnForecastModel } from '../api/returnForecastModels'
import { ModelTrainingLaunchDialog, type ModelTrainingLaunchPayload } from '../components/ModelTrainingLaunchDialog'
import type { ModelLaunchResultState, ModelLaunchWizardState } from './modelLaunchRoutes'
import { familyListPath } from './modelLaunchRoutes'

export function ReturnForecastModelWizardPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const launchState = (location.state as ModelLaunchWizardState | null) ?? null
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(payload: ModelTrainingLaunchPayload) {
    if (payload.family !== 'return_forecast') {
      return
    }
    const sourceIds = launchState?.sourceIds ?? []
    if (sourceIds.length === 0) {
      setError(`Select at least one ${launchState?.selectionLabel ?? 'source'} first.`)
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const response = await createReturnForecastModel({
        ...(payload.request as any),
        ...(launchState?.sourceKind === 'dataset'
          ? { dataset_ids: sourceIds }
          : { backtest_ids: sourceIds }),
      })
      navigate(familyListPath('return_forecast'), {
        state: {
          launchResult: {
            status: 'success',
            family: 'return_forecast',
            message: 'Return forecast model launch submitted successfully.',
            groupId: response.group_id,
            modelName: response.name ?? null,
          } satisfies ModelLaunchResultState,
        },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create return forecast model')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ModelTrainingLaunchDialog
      open
      allowedFamilies={['return_forecast']}
      selectedCount={launchState?.selectedCount ?? 0}
      selectionLabel={launchState?.selectionLabel ?? 'sources'}
      submitting={submitting}
      error={error}
      onClose={() => navigate(familyListPath('return_forecast'))}
      onSubmit={handleSubmit}
    />
  )
}
