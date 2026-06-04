import {
  deleteRiskModel,
  fetchRiskModelStatus,
  fetchRiskModels,
  fetchRiskModelWorkflowErrors,
  retryRiskModel,
} from '../api/riskModels'
import { createModelListPage } from './modelFamilyPages'

const RiskModelsListPageImpl = createModelListPage({
  singularLabel: 'Risk model',
  pluralLabel: 'Risk models',
  listPath: '/models/risk',
  fetchModels: fetchRiskModels,
  fetchModelStatus: fetchRiskModelStatus,
  fetchModelWorkflowErrors: fetchRiskModelWorkflowErrors,
  retryModel: retryRiskModel,
  deleteModel: deleteRiskModel,
})

export function RiskModelsListPage() {
  return <RiskModelsListPageImpl />
}
