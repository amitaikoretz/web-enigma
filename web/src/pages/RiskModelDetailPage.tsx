import {
  fetchRiskModelDetail,
  fetchRiskModelStatus,
  fetchRiskModelWorkflowErrors,
} from '../api/riskModels'
import { createModelDetailPage } from './modelFamilyPages'

const RiskModelDetailPageImpl = createModelDetailPage({
  singularLabel: 'Risk model',
  pluralLabel: 'Risk models',
  listPath: '/models/risk',
  fetchModelStatus: fetchRiskModelStatus,
  fetchModelDetail: fetchRiskModelDetail,
  fetchModelWorkflowErrors: fetchRiskModelWorkflowErrors,
})

export function RiskModelDetailPage() {
  return <RiskModelDetailPageImpl />
}
