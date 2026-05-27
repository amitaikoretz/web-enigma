#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/k8s_kubectl.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/k8s_kubectl.sh"

# Print colored api-serve prerequisites and runtime configuration.
# Expects DATABASE_URL, REDIS_URL, BACKTEST_RESULTS_DIR, ARGO_NAMESPACE,
# API_HOST, API_PORT, and optionally ARGO_SERVER_URL in the environment.

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  CYAN=$'\033[36m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  BLUE=$'\033[34m'
  MAGENTA=$'\033[35m'
  RED=$'\033[31m'
  RESET=$'\033[0m'
else
  BOLD='' DIM='' CYAN='' GREEN='' YELLOW='' BLUE='' MAGENTA='' RED='' RESET=''
fi

K8S_NAMESPACE="${K8S_NAMESPACE:-backtest}"
ARGO_NAMESPACE="${ARGO_NAMESPACE:-backtest-workflows}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
API_PORT_FORWARDS_SESSION="${API_PORT_FORWARDS_SESSION:-bt-port-forwards}"
POSTGRES_LOCAL_PORT="${POSTGRES_LOCAL_PORT:-5432}"
REDIS_LOCAL_PORT="${REDIS_LOCAL_PORT:-6379}"
ARGO_SERVER_PORT="${ARGO_SERVER_PORT:-2746}"

status_ok() { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
status_warn() { printf '  %s⚠%s %s\n' "$YELLOW" "$RESET" "$1"; }
status_fail() { printf '  %s✗%s %s\n' "$RED" "$RESET" "$1"; }

cmd() { printf '     %s$%s %s\n' "$DIM" "$RESET" "$1"; }

tcp_open() {
  local host="$1" port="$2"
  (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1
}

section() {
  printf '\n  %s%s%s\n' "$BOLD" "$1" "$RESET"
}

rule() {
  printf '  %s────────────────────────────────────────────────────────%s\n' "$DIM" "$RESET"
}

printf '\n%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$CYAN" "$RESET"
printf '%s  api-serve%s  %s·%s  local API against k3s / Docker + Argo Workflows\n' "$BOLD" "$RESET" "$DIM" "$RESET"
printf '%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$CYAN" "$RESET"

section '1. Kubernetes stack'
printf '   Deploy the backtest namespace (Postgres, Redis, workloads):\n'
cmd 'make k3s-deploy'
if command -v kubectl >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
  status_ok 'kubectl can reach the cluster'
  if kubectl get namespace "$K8S_NAMESPACE" >/dev/null 2>&1; then
    status_ok "namespace ${K8S_NAMESPACE} exists"
  else
    status_warn "namespace ${K8S_NAMESPACE} not found — run make k3s-deploy"
  fi
else
  status_fail 'kubectl is missing or cannot reach a cluster'
fi

section '2. Argo Workflows'
printf '   Bootstrap the workflow namespace and RBAC:\n'
cmd 'make bootstrap-backtest-workflows-namespace'
if command -v kubectl >/dev/null 2>&1 && kubectl get namespace "$ARGO_NAMESPACE" >/dev/null 2>&1; then
  status_ok "namespace ${ARGO_NAMESPACE} exists"
else
  status_warn "namespace ${ARGO_NAMESPACE} not found — run make bootstrap-backtest-workflows-namespace"
fi

section '3. Port-forwards'
printf '   Start all cluster port-forwards in tmux (postgres, redis, argo-server):\n'
cmd 'make api-port-forwards'
if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$API_PORT_FORWARDS_SESSION" 2>/dev/null; then
  status_ok "tmux session ${API_PORT_FORWARDS_SESSION} is running"
else
  status_warn "tmux session ${API_PORT_FORWARDS_SESSION} is not running — run make api-port-forwards"
fi
if tcp_open localhost "$POSTGRES_LOCAL_PORT"; then
  status_ok "localhost:${POSTGRES_LOCAL_PORT} is reachable (Postgres)"
else
  status_warn "localhost:${POSTGRES_LOCAL_PORT} is not reachable — run make api-port-forwards"
fi
if tcp_open localhost "$REDIS_LOCAL_PORT"; then
  status_ok "localhost:${REDIS_LOCAL_PORT} is reachable (Redis)"
else
  status_warn "localhost:${REDIS_LOCAL_PORT} is not reachable — run make api-port-forwards"
fi
if tcp_open localhost "$ARGO_SERVER_PORT"; then
  status_ok "localhost:${ARGO_SERVER_PORT} is reachable (Argo Server)"
else
  status_warn "localhost:${ARGO_SERVER_PORT} is not reachable — run make api-port-forwards"
fi

section '4. Argo workflow submission'
if [[ -n "${ARGO_SERVER_URL:-}" ]]; then
  printf '   Using Argo Server HTTP:\n'
  status_ok "ARGO_SERVER_URL=${ARGO_SERVER_URL}"
else
  printf '   Using kubeconfig (default for Rancher Desktop k3s):\n'
  status_ok 'workflows submitted via kubectl → local cluster'
  printf '     %sTip:%s make api-serve ARGO_SERVER_URL=http://localhost:%s after make api-port-forwards\n' \
    "$DIM" "$RESET" "$ARGO_SERVER_PORT"
fi

rule
printf '\n  %sStarting API%s  %shttp://%s:%s%s\n' "$BOLD" "$RESET" "$GREEN" "$API_HOST" "$API_PORT" "$RESET"
printf '  %sDATABASE_URL%s=%s\n' "$CYAN" "$RESET" "${DATABASE_URL:-<unset>}"
printf '  %sREDIS_URL%s=%s\n' "$CYAN" "$RESET" "${REDIS_URL:-<unset>}"
printf '  %sBACKTEST_RESULTS_DIR%s=%s\n' "$CYAN" "$RESET" "${BACKTEST_RESULTS_DIR:-<unset>}"
printf '  %sARGO_NAMESPACE%s=%s\n' "$CYAN" "$RESET" "$ARGO_NAMESPACE"
if [[ -n "${ARGO_SERVER_URL:-}" ]]; then
  printf '  %sARGO_SERVER_URL%s=%s\n' "$CYAN" "$RESET" "$ARGO_SERVER_URL"
fi
printf '\n'
