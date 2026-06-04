import {
  deleteReturnForecastModel,
  fetchReturnForecastModelStatus,
  fetchReturnForecastModelWorkflowErrors,
  fetchReturnForecastModels,
  retryReturnForecastModel,
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
})

export function ReturnForecastModelsListPage() {
  return <ReturnForecastModelsListPageImpl />
}
