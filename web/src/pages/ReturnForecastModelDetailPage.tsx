import {
  deleteReturnForecastModel,
  fetchReturnForecastModelDetail,
  fetchReturnForecastModelStatus,
  fetchReturnForecastModelWorkflowErrors,
  updateReturnForecastModel,
} from '../api/returnForecastModels'
import { createModelDetailPage } from './modelFamilyPages'

const ReturnForecastModelDetailPageImpl = createModelDetailPage({
  singularLabel: 'Return forecast model',
  pluralLabel: 'Return forecast models',
  listPath: '/models/returns',
  fetchModelStatus: fetchReturnForecastModelStatus,
  fetchModelDetail: fetchReturnForecastModelDetail,
  fetchModelWorkflowErrors: fetchReturnForecastModelWorkflowErrors,
  deleteModel: deleteReturnForecastModel,
  updateModelName: (groupId, name) => updateReturnForecastModel(groupId, { name }),
})

export function ReturnForecastModelDetailPage() {
  return <ReturnForecastModelDetailPageImpl />
}
