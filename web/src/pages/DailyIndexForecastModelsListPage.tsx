import {
  deleteDailyIndexForecastModel,
  fetchDailyIndexForecastModelStatus,
  fetchDailyIndexForecastModels,
  fetchDailyIndexForecastModelWorkflowErrors,
  retryDailyIndexForecastModel,
} from '../api/dailyIndexForecastModels'
import { DailyIndexForecastModelsListPage as DailyIndexForecastModelsListPageImpl } from './DailyIndexForecastModelPages'

export function DailyIndexForecastModelsListPage() {
  return (
    <DailyIndexForecastModelsListPageImpl
      fetchModels={fetchDailyIndexForecastModels}
      fetchModelStatus={fetchDailyIndexForecastModelStatus}
      fetchModelWorkflowErrors={fetchDailyIndexForecastModelWorkflowErrors}
      retryModel={retryDailyIndexForecastModel}
      deleteModel={deleteDailyIndexForecastModel}
    />
  )
}

