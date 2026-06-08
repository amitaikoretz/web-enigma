import {
  deleteRiskModel,
  fetchRiskModelDetail,
  fetchRiskModelStatus,
  fetchRiskModelWorkflowErrors,
  retryRiskModel,
  updateRiskModel,
} from '../api/riskModels'
import { createModelDetailPage } from './modelFamilyPages'

const RiskModelDetailPageImpl = createModelDetailPage({
  singularLabel: 'Risk model',
  pluralLabel: 'Risk models',
  listPath: '/models/risk',
  fetchModelStatus: fetchRiskModelStatus,
  fetchModelDetail: fetchRiskModelDetail,
  fetchModelWorkflowErrors: fetchRiskModelWorkflowErrors,
  deleteModel: deleteRiskModel,
  retryModel: retryRiskModel,
  updateModelName: (groupId, name) => updateRiskModel(groupId, { name }),
})

export function RiskModelDetailPage() {
  return <RiskModelDetailPageImpl />
}
