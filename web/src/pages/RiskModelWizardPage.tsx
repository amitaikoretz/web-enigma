import { createRiskModel } from '../api/riskModels'
import { ModelTrainingLaunchDialog, type ModelTrainingLaunchPayload } from '../components/ModelTrainingLaunchDialog'
import { useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import type { ModelLaunchResultState, ModelLaunchWizardState } from './modelLaunchRoutes'
import { familyListPath } from './modelLaunchRoutes'

export function RiskModelWizardPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const launchState = (location.state as ModelLaunchWizardState | null) ?? null
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(payload: ModelTrainingLaunchPayload) {
    if (payload.family !== 'risk') {
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
      const response = await createRiskModel({
        ...(payload.request as any),
        ...(launchState?.sourceKind === 'dataset'
          ? { dataset_ids: sourceIds }
          : { backtest_ids: sourceIds }),
      })
      navigate(familyListPath('risk'), {
        state: {
          launchResult: {
            status: 'success',
            family: 'risk',
            message: 'Risk model launch submitted successfully.',
            groupId: response.group_id,
            modelName: response.name ?? null,
          } satisfies ModelLaunchResultState,
        },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create risk model')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ModelTrainingLaunchDialog
      open
      allowedFamilies={['risk']}
      selectedCount={launchState?.selectedCount ?? 0}
      selectionLabel={launchState?.selectionLabel ?? 'sources'}
      submitting={submitting}
      error={error}
      onClose={() => navigate(familyListPath('risk'))}
      onSubmit={handleSubmit}
    />
  )
}
