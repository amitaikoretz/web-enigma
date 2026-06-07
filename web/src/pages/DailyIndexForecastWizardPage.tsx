import { createDailyIndexForecastModel } from '../api/dailyIndexForecastModels'
import { DailyIndexForecastModelWizardPage as DailyIndexForecastModelWizardPageImpl } from './DailyIndexForecastModelPages'

export function DailyIndexForecastWizardPage() {
  return <DailyIndexForecastModelWizardPageImpl createModel={createDailyIndexForecastModel} />
}

