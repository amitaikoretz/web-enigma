import {
  fetchDailyIndexForecastModelDetail,
  fetchDailyIndexForecastModelStatus,
  fetchDailyIndexForecastModelWorkflowErrors,
  updateDailyIndexForecastModel,
} from '../api/dailyIndexForecastModels'
import { DailyIndexForecastModelDetailPage as DailyIndexForecastModelDetailPageImpl } from './DailyIndexForecastModelPages'

export function DailyIndexForecastModelDetailPage() {
  return (
    <DailyIndexForecastModelDetailPageImpl
      fetchModelDetail={fetchDailyIndexForecastModelDetail}
      fetchModelStatus={fetchDailyIndexForecastModelStatus}
      fetchModelWorkflowErrors={fetchDailyIndexForecastModelWorkflowErrors}
      updateModelName={(groupId, name) => updateDailyIndexForecastModel(groupId, { name })}
    />
  )
}

