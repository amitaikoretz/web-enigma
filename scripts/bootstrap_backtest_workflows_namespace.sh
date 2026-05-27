#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/k8s_kubectl.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/k8s_kubectl.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW_NAMESPACE="${WORKFLOW_NAMESPACE:-backtest-workflows}"

kubectl apply -k "${ROOT}/deploy/k8s/workflows"

if kubectl get secret app-secrets -n backtest >/dev/null 2>&1; then
  echo "Copying app-secrets from namespace backtest -> ${WORKFLOW_NAMESPACE}"
  kubectl get secret app-secrets -n backtest -o yaml \
    | sed '/resourceVersion:/d;/uid:/d;/creationTimestamp:/d' \
    | sed "s/namespace: backtest/namespace: ${WORKFLOW_NAMESPACE}/" \
    | kubectl apply -f -
else
  echo "No app-secrets in namespace backtest; create one in ${WORKFLOW_NAMESPACE} before running Alpaca backtests."
fi

echo ""
echo "Workflow namespace ready. Configure the API with:"
echo "  ARGO_NAMESPACE=${WORKFLOW_NAMESPACE}"
echo "  ARGO_WORKFLOW_SERVICE_ACCOUNT=backtest-workflow"
