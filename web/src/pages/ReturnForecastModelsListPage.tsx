import {
  deleteReturnForecastModel,
  fetchReturnForecastModelStatus,
  fetchReturnForecastModelWorkflowErrors,
  fetchReturnForecastModels,
  retryReturnForecastModel,
  updateReturnForecastModel,
} from '../api/returnForecastModels'
import { createModelListPage } from './modelFamilyPages'

const ReturnForecastModelsListPageImpl = createModelListPage({
  singularLabel: 'Return forecast model',
  pluralLabel: 'Return forecast models',
  listPath: '/models/returns',
  fetchModels: fetchReturnForecastModels,
  fetchModelStatus: fetchReturnForecastModelStatus,
  fetchModelWorkflowErrors: fetchReturnForecastModelWorkflowErrors,
  retryModel: retryReturnForecastModel,
  deleteModel: deleteReturnForecastModel,
  updateModelName: (groupId, name) => updateReturnForecastModel(groupId, { name }),
})

export function ReturnForecastModelsListPage() {
  return <ReturnForecastModelsListPageImpl />
}
