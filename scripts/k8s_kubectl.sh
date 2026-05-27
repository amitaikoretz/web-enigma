_K8S_KUBECTL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${K8S_CONTEXT:-}" ]]; then
  # shellcheck source=scripts/k8s.env
  source "${_K8S_KUBECTL_DIR}/k8s.env"
fi
kubectl() { command kubectl --context "$K8S_CONTEXT" "$@"; }
