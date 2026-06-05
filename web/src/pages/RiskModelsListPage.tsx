import {
  deleteRiskModel,
  fetchRiskModelStatus,
  fetchRiskModels,
  fetchRiskModelWorkflowErrors,
  retryRiskModel,
  updateRiskModel,
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
  updateModelName: (groupId, name) => updateRiskModel(groupId, { name }),
})

export function RiskModelsListPage() {
  return <RiskModelsListPageImpl />
}
