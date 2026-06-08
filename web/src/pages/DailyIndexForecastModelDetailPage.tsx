import {
  deleteDailyIndexForecastModel,
  fetchDailyIndexForecastModelDetail,
  fetchDailyIndexForecastModelStatus,
  fetchDailyIndexForecastModelWorkflowErrors,
  retryDailyIndexForecastModel,
  updateDailyIndexForecastModel,
} from '../api/dailyIndexForecastModels'
import { DailyIndexForecastModelDetailPage as DailyIndexForecastModelDetailPageImpl } from './DailyIndexForecastModelPages'

export function DailyIndexForecastModelDetailPage() {
  return (
    <DailyIndexForecastModelDetailPageImpl
      fetchModelDetail={fetchDailyIndexForecastModelDetail}
      fetchModelStatus={fetchDailyIndexForecastModelStatus}
      fetchModelWorkflowErrors={fetchDailyIndexForecastModelWorkflowErrors}
      retryModel={retryDailyIndexForecastModel}
      deleteModel={deleteDailyIndexForecastModel}
      updateModelName={(groupId, name) => updateDailyIndexForecastModel(groupId, { name })}
    />
  )
}
