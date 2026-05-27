#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/k8s_kubectl.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/k8s_kubectl.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K8S_NAMESPACE="${K8S_NAMESPACE:-backtest}"
WORKFLOW_NAMESPACE="${WORKFLOW_NAMESPACE:-backtest-workflows}"
SECRET_NAME="${SECRET_NAME:-app-secrets}"
DEFAULT_DATABASE_URL="postgresql+psycopg://postgres:postgres@postgres:5432/backtest"

if [[ -z "${ALPACA_API_KEY:-}" || -z "${ALPACA_SECRET_KEY:-}" ]] && [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi

if [[ -z "${ALPACA_API_KEY:-}" || -z "${ALPACA_SECRET_KEY:-}" ]]; then
  echo "Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY in your shell or repo-root .env" >&2
  exit 1
fi

if ! kubectl get namespace "${K8S_NAMESPACE}" >/dev/null 2>&1; then
  echo "Namespace ${K8S_NAMESPACE} not found; deploy the local overlay first (make k3s-deploy)." >&2
  exit 1
fi

existing_database_url=""
if kubectl get secret "${SECRET_NAME}" -n "${K8S_NAMESPACE}" >/dev/null 2>&1; then
  existing_database_url="$(kubectl get secret "${SECRET_NAME}" -n "${K8S_NAMESPACE}" \
    -o jsonpath='{.data.DATABASE_URL}' 2>/dev/null | base64 -d 2>/dev/null || true)"
fi
database_url="${existing_database_url:-${DATABASE_URL:-${DEFAULT_DATABASE_URL}}}"

echo "Updating secret/${SECRET_NAME} in namespace ${K8S_NAMESPACE}"
kubectl create secret generic "${SECRET_NAME}" \
  -n "${K8S_NAMESPACE}" \
  --from-literal=DATABASE_URL="${database_url}" \
  --from-literal=ALPACA_API_KEY="${ALPACA_API_KEY}" \
  --from-literal=ALPACA_SECRET_KEY="${ALPACA_SECRET_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

if kubectl get namespace "${WORKFLOW_NAMESPACE}" >/dev/null 2>&1; then
  echo "Copying secret/${SECRET_NAME} from ${K8S_NAMESPACE} -> ${WORKFLOW_NAMESPACE}"
  kubectl get secret "${SECRET_NAME}" -n "${K8S_NAMESPACE}" -o yaml \
    | sed '/resourceVersion:/d;/uid:/d;/creationTimestamp:/d' \
    | sed "s/namespace: ${K8S_NAMESPACE}/namespace: ${WORKFLOW_NAMESPACE}/" \
    | kubectl apply -f -
else
  echo "Namespace ${WORKFLOW_NAMESPACE} not found; skipping workflow secret copy." >&2
  echo "Run make bootstrap-backtest-workflows-namespace before Argo backtests that use Alpaca data." >&2
fi

echo "Restarting workloads in ${K8S_NAMESPACE} to reload credentials"
kubectl -n "${K8S_NAMESPACE}" rollout restart deployment/api deployment/controller deployment/web statefulset/worker
kubectl -n "${K8S_NAMESPACE}" rollout status deployment/api --timeout=180s
kubectl -n "${K8S_NAMESPACE}" rollout status deployment/controller --timeout=180s
kubectl -n "${K8S_NAMESPACE}" rollout status deployment/web --timeout=180s
kubectl -n "${K8S_NAMESPACE}" rollout status statefulset/worker --timeout=240s

echo ""
echo "Alpaca credentials synced to secret/${SECRET_NAME} (API, controller, workers, and workflow pods)."
echo "New Argo workflow pods in ${WORKFLOW_NAMESPACE} will pick up the updated secret automatically."
echo "Re-submit any already-running workflows if they were started before this sync."
