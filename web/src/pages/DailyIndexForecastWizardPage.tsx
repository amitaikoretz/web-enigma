import { useLocation } from 'react-router-dom'

import { createDailyIndexForecastModel } from '../api/dailyIndexForecastModels'
import { DailyIndexForecastModelWizardPage as DailyIndexForecastModelWizardPageImpl } from './DailyIndexForecastModelPages'
import type { DailyIndexDatasetSource } from '../components/ModelTrainingLaunchDialog'
import type { ModelLaunchWizardState } from './modelLaunchRoutes'

export function DailyIndexForecastWizardPage() {
  const location = useLocation()
  const launchState = (location.state as ModelLaunchWizardState | null) ?? null
  const dailyIndexDatasetSource: DailyIndexDatasetSource | null =
    launchState?.dailyIndexDatasetSource ?? null
  const dailyIndexDatasetId = launchState?.sourceKind === 'dataset' ? launchState.sourceIds[0] ?? null : null

  return (
    <DailyIndexForecastModelWizardPageImpl
      createModel={createDailyIndexForecastModel}
      dailyIndexDatasetSource={dailyIndexDatasetSource}
      dailyIndexDatasetId={dailyIndexDatasetId}
    />
  )
}
