import { fetchRiskModelWorkflowErrors } from '../api/riskModels'
import { ModelWorkflowErrorDialog } from './ModelWorkflowErrorDialog'

interface RiskModelWorkflowErrorDialogProps {
  groupId: string | null
  open: boolean
  onClose: () => void
}

export function RiskModelWorkflowErrorDialog({
  groupId,
  open,
  onClose,
}: RiskModelWorkflowErrorDialogProps) {
  return (
    <ModelWorkflowErrorDialog
      groupId={groupId}
      open={open}
      onClose={onClose}
      entityKind="Risk model"
      entityLabel={groupId ? `Risk model ${groupId}` : 'Risk model'}
      fetchWorkflowErrors={fetchRiskModelWorkflowErrors}
    />
  )
}
