#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/k8s_kubectl.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/k8s_kubectl.sh"

# Start kubectl port-forwards for api-serve in a detached tmux session.
# One window with a pane per forward: postgres, redis, argo-server (when found).

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  CYAN=$'\033[36m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  RESET=$'\033[0m'
else
  BOLD='' DIM='' CYAN='' GREEN='' YELLOW='' RED='' RESET=''
fi

K8S_NAMESPACE="${K8S_NAMESPACE:-backtest}"
SESSION="${API_PORT_FORWARDS_SESSION:-bt-port-forwards}"
POSTGRES_LOCAL_PORT="${POSTGRES_LOCAL_PORT:-5432}"
REDIS_LOCAL_PORT="${REDIS_LOCAL_PORT:-6379}"
ARGO_SERVER_PORT="${ARGO_SERVER_PORT:-2746}"
POSTGRES_SERVICE_PORT="${POSTGRES_SERVICE_PORT:-5432}"
REDIS_SERVICE_PORT="${REDIS_SERVICE_PORT:-6379}"
ARGO_SERVER_SERVICE_PORT="${ARGO_SERVER_SERVICE_PORT:-2746}"
ARGO_K8S_NAMESPACE="${ARGO_K8S_NAMESPACE:-}"
ARGO_SERVER_SERVICE_NAME="${ARGO_SERVER_SERVICE_NAME:-}"

status_ok() { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
status_warn() { printf '  %s⚠%s %s\n' "$YELLOW" "$RESET" "$1"; }
status_fail() { printf '  %s✗%s %s\n' "$RED" "$RESET" "$1"; }

if ! command -v tmux >/dev/null 2>&1; then
  status_fail 'tmux is not installed — install tmux or run port-forwards manually'
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1 || ! kubectl cluster-info >/dev/null 2>&1; then
  status_fail 'kubectl is missing or cannot reach a cluster'
  exit 1
fi

argo_server_service_names() {
  if [[ -n "$ARGO_SERVER_SERVICE_NAME" ]]; then
    printf '%s' "$ARGO_SERVER_SERVICE_NAME"
  else
    printf '%s' 'argo-server argo-workflows-server'
  fi
}

argo_server_namespaces() {
  if [[ -n "$ARGO_K8S_NAMESPACE" ]]; then
    printf '%s' "$ARGO_K8S_NAMESPACE"
  else
    printf '%s' 'argo argo-workflows'
  fi
}

# Print namespace/service on success.
detect_argo_server() {
  local ns svc names checked_ns checked_svc
  read -r -a names <<< "$(argo_server_service_names)"
  read -r -a checked_ns <<< "$(argo_server_namespaces)"

  for ns in "${checked_ns[@]}"; do
    for svc in "${names[@]}"; do
      if kubectl get svc "$svc" -n "$ns" >/dev/null 2>&1; then
        printf '%s:%s' "$ns" "$svc"
        return 0
      fi
    done
  done

  if [[ -n "$ARGO_K8S_NAMESPACE" || -n "$ARGO_SERVER_SERVICE_NAME" ]]; then
    status_warn "Argo server not found for ARGO_K8S_NAMESPACE=${ARGO_K8S_NAMESPACE:-<auto>} ARGO_SERVER_SERVICE_NAME=${ARGO_SERVER_SERVICE_NAME:-<auto>}"
  fi
  return 1
}

for svc in postgres redis; do
  if ! kubectl get svc "$svc" -n "$K8S_NAMESPACE" >/dev/null 2>&1; then
    status_fail "service ${svc} not found in namespace ${K8S_NAMESPACE} — run make k3s-deploy"
    exit 1
  fi
done

ARGO_NS=""
ARGO_SVC=""
if detected="$(detect_argo_server)"; then
  ARGO_NS="${detected%%:*}"
  ARGO_SVC="${detected#*:}"
else
  status_warn 'Argo server service not found — skipping Argo port-forward (tried argo-server and argo-workflows-server in argo, argo-workflows)'
fi

printf '\n%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$CYAN" "$RESET"
printf '%s  api-port-forwards%s  %s·%s  starting kubectl port-forwards in tmux\n' "$BOLD" "$RESET" "$DIM" "$RESET"
printf '%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n\n' "$CYAN" "$RESET"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
  status_ok "replaced existing tmux session ${SESSION}"
fi

WINDOW=port-forwards
PG_CMD="kubectl --context ${K8S_CONTEXT} -n ${K8S_NAMESPACE} port-forward svc/postgres ${POSTGRES_LOCAL_PORT}:${POSTGRES_SERVICE_PORT}; exec bash"
REDIS_CMD="kubectl --context ${K8S_CONTEXT} -n ${K8S_NAMESPACE} port-forward svc/redis ${REDIS_LOCAL_PORT}:${REDIS_SERVICE_PORT}; exec bash"

tmux new-session -d -s "$SESSION" -n "$WINDOW" "$PG_CMD"
status_ok "postgres  localhost:${POSTGRES_LOCAL_PORT} → ${K8S_NAMESPACE}/svc/postgres:${POSTGRES_SERVICE_PORT}"

tmux split-window -h -t "${SESSION}:${WINDOW}" "$REDIS_CMD"
status_ok "redis     localhost:${REDIS_LOCAL_PORT} → ${K8S_NAMESPACE}/svc/redis:${REDIS_SERVICE_PORT}"

if [[ -n "$ARGO_NS" && -n "$ARGO_SVC" ]]; then
  ARGO_CMD="kubectl --context ${K8S_CONTEXT} -n ${ARGO_NS} port-forward svc/${ARGO_SVC} ${ARGO_SERVER_PORT}:${ARGO_SERVER_SERVICE_PORT}; exec bash"
  tmux split-window -v -t "${SESSION}:${WINDOW}.1" "$ARGO_CMD"
  status_ok "argo      localhost:${ARGO_SERVER_PORT} → ${ARGO_NS}/svc/${ARGO_SVC}:${ARGO_SERVER_SERVICE_PORT}"
  tmux select-layout -t "${SESSION}:${WINDOW}" tiled
else
  tmux select-layout -t "${SESSION}:${WINDOW}" even-horizontal
fi

printf '\n  %sSession:%s  %s\n' "$BOLD" "$RESET" "$SESSION"
printf '  %sAttach:%s  tmux attach -t %s\n' "$BOLD" "$RESET" "$SESSION"
printf '  %sStop:%s    make api-port-forwards-stop\n' "$BOLD" "$RESET"
if [[ -n "$ARGO_NS" && -n "$ARGO_SVC" ]]; then
  printf '  %sArgo URL:%s  http://localhost:%s  (make api-serve sets ARGO_SERVER_URL=http://localhost:%s)\n' \
    "$BOLD" "$RESET" "$ARGO_SERVER_PORT" "$ARGO_SERVER_PORT"
fi
printf '\n'
