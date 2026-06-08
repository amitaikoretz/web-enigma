import { Navigate, useLocation } from 'react-router-dom'

import type { DailyIndexDatasetSource } from '../components/ModelTrainingLaunchDialog'

export type ModelWizardFamily = 'risk' | 'return_forecast' | 'daily_index_forecast'
export type ModelLaunchSourceKind = 'backtest' | 'dataset'

export interface ModelLaunchWizardState {
  sourceKind: ModelLaunchSourceKind
  sourceIds: string[]
  selectedCount: number
  selectionLabel: string
  dailyIndexDatasetSource?: DailyIndexDatasetSource | null
}

export interface ModelLaunchResultState {
  status: 'success' | 'failed'
  family: ModelWizardFamily
  message: string
  groupId?: string
  featureRunId?: string
  modelName?: string | null
}

export function familyLabel(family: ModelWizardFamily): string {
  if (family === 'risk') return 'Risk model'
  if (family === 'return_forecast') return 'Return forecast model'
  return 'Daily Index Forecast'
}

export function familyListSearchParam(family: ModelWizardFamily): string {
  if (family === 'risk') return 'risk'
  if (family === 'return_forecast') return 'returns'
  return 'daily-index'
}

export function familyListPath(family: ModelWizardFamily): string {
  return `/models?family=${familyListSearchParam(family)}`
}

export function familyDetailPath(family: ModelWizardFamily, groupId: string): string {
  if (family === 'risk') return `/models/risk/${groupId}`
  if (family === 'return_forecast') return `/models/returns/${groupId}`
  return `/models/daily-index/${groupId}`
}

export function familyWizardPath(family: ModelWizardFamily): string {
  if (family === 'risk') return '/models/risk/new'
  if (family === 'return_forecast') return '/models/returns/new'
  return '/models/daily-index/new'
}

export function ModelsFamilyRedirect({ family }: { family: ModelWizardFamily }) {
  const location = useLocation()
  return <Navigate to={familyListPath(family)} replace state={location.state} />
}
