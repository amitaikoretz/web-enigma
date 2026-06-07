# Local k3s image names (see deploy/k8s/base/kustomization.yaml)
APP_IMAGE ?= backtest-app:latest
WEB_IMAGE ?= backtest-web:latest

# Third-party images referenced by deploy/k8s/overlays/local
K8S_DEP_IMAGES ?= postgres:16-alpine redis:7-alpine busybox:1.36

# Rancher Desktop k3s reads images from the containerd k8s.io namespace.
# Use `make K8S_BUILD=docker k8s-local-images` when RD is set to the Moby (dockerd) runtime.
K8S_BUILD ?= nerdctl
K8S_LOCAL_OVERLAY ?= deploy/k8s/overlays/local
K8S_NAMESPACE ?= backtest

include scripts/k8s.env
export K8S_CONTEXT
KUBECTL := kubectl --context $(K8S_CONTEXT)

# Host-run API (make api-serve) — expects k3s/docker stack + Argo Workflows already running.
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
ARGO_NAMESPACE ?= backtest-workflows
ARGO_WORKFLOW_SERVICE_ACCOUNT ?= backtest-workflow
# Host paths mounted into k3s via hostPath PVs (Mac-visible when under ~/… on Rancher Desktop).
HOST_BACKTEST_RESULTS ?= $(abspath $(CURDIR)/data/backtest-results)
HOST_BACKTEST_CACHE ?= $(abspath $(CURDIR)/data/backtest-cache)
# Local ports (host side of make api-port-forwards).
POSTGRES_LOCAL_PORT ?= 54321
REDIS_LOCAL_PORT ?= 63791
ARGO_SERVER_PORT ?= 27461
# Cluster service ports (remote side of kubectl port-forward).
POSTGRES_SERVICE_PORT ?= 5432
REDIS_SERVICE_PORT ?= 6379
ARGO_SERVER_SERVICE_PORT ?= 2746
# Host-run API talks to Argo only via HTTP (see make api-port-forwards).
ARGO_SERVER_URL ?= http://localhost:$(ARGO_SERVER_PORT)
API_PORT_FORWARDS_SESSION ?= bt-port-forwards
# Leave empty to auto-detect (namespace: argo or argo-workflows; service: argo-server or argo-workflows-server).
ARGO_K8S_NAMESPACE ?=
ARGO_SERVER_SERVICE_NAME ?=

API_DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:$(POSTGRES_LOCAL_PORT)/backtest
API_REDIS_URL ?= redis://localhost:$(REDIS_LOCAL_PORT)/0
API_RESULTS_DIR ?= $(HOST_BACKTEST_RESULTS)
API_CACHE_DIR ?= $(HOST_BACKTEST_CACHE)

ifeq ($(K8S_BUILD),nerdctl)
  K8S_CLI := nerdctl --namespace k8s.io
else
  K8S_CLI := docker
endif

.DEFAULT_GOAL := help

.PHONY: help api-serve api-port-forwards api-port-forwards-stop k8s-local-images build-k8s-app build-k8s-web pull-k8s-deps k3s-deploy k3s-apply-host-volumes k3s-recreate-host-volumes k8s-restart-workloads k8s-workflows-deploy k8s-workflows-deploy-local test-argo-inline bootstrap-backtest-workflows-namespace sync-app-secrets open-results

help: ## List available targets (default)
	@printf '\n'
	@printf '  %-32s  %s\n' 'Target' 'Description'
	@printf '  %-32s  %s\n' '------' '-----------'
	@grep -hE '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  %-32s  %s\n", $$1, $$2}' \
		| sort
	@printf '\n'
	@printf '  Variables: K8S_BUILD=%s  K8S_CONTEXT=%s  K8S_NAMESPACE=%s  K8S_LOCAL_OVERLAY=%s\n' \
		'$(K8S_BUILD)' '$(K8S_CONTEXT)' '$(K8S_NAMESPACE)' '$(K8S_LOCAL_OVERLAY)'
	@printf '             APP_IMAGE=%s  WEB_IMAGE=%s\n' '$(APP_IMAGE)' '$(WEB_IMAGE)'
	@printf '             HOST_BACKTEST_RESULTS=%s\n' '$(HOST_BACKTEST_RESULTS)'
	@printf '             api-serve: API_HOST=%s  API_PORT=%s  ARGO_SERVER_URL=%s\n' \
		'$(API_HOST)' '$(API_PORT)' '$(ARGO_SERVER_URL)'
	@printf '             api-port-forwards: SESSION=%s  POSTGRES_LOCAL_PORT=%s  REDIS_LOCAL_PORT=%s  ARGO_SERVER_PORT=%s\n\n' \
		'$(API_PORT_FORWARDS_SESSION)' '$(POSTGRES_LOCAL_PORT)' '$(REDIS_LOCAL_PORT)' '$(ARGO_SERVER_PORT)'

k8s-local-images: build-k8s-app build-k8s-web pull-k8s-deps ## Build app/web images and pull third-party k8s images
	@echo ""
	@echo "Deploy with:"
	@echo "  make k3s-deploy"

build-k8s-app: ## Build the API container image (APP_IMAGE)
	$(K8S_CLI) build -t $(APP_IMAGE) .

build-k8s-web: ## Build the web UI container image (WEB_IMAGE)
	$(K8S_CLI) build -t $(WEB_IMAGE) -f web/Dockerfile web/

pull-k8s-deps: ## Pull postgres, redis, and busybox images for local k8s
	@for img in $(K8S_DEP_IMAGES); do \
		echo "Pulling $$img"; \
		$(K8S_CLI) pull $$img; \
	done

k8s-restart-workloads: ## Rollout restart api, controller, web, and worker in K8S_NAMESPACE
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout restart deployment/api deployment/controller deployment/web statefulset/worker
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status deployment/api --timeout=180s
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status deployment/controller --timeout=180s
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status deployment/web --timeout=180s
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status statefulset/worker --timeout=240s

k3s-apply-host-volumes: ## Apply hostPath PVs bound to Mac-visible directories (HOST_BACKTEST_*)
	@mkdir -p "$(HOST_BACKTEST_RESULTS)" "$(HOST_BACKTEST_CACHE)"
	@export HOST_BACKTEST_RESULTS="$(HOST_BACKTEST_RESULTS)" HOST_BACKTEST_CACHE="$(HOST_BACKTEST_CACHE)"; \
		envsubst < deploy/k8s/overlays/local/pv-hostpath.yaml.in | $(KUBECTL) apply -f -
	@printf 'Host results (Mac + cluster): %s\n' "$(HOST_BACKTEST_RESULTS)"
	@printf 'Host cache (Mac + cluster):   %s\n' "$(HOST_BACKTEST_CACHE)"

k3s-recreate-host-volumes: ## Delete old PVCs and redeploy hostPath volumes (copies nothing; use before first migrate)
	@printf 'WARNING: deletes backtest-results and backtest-cache PVCs in %s and backtest-workflows. Scale down API first if needed.\n' "$(K8S_NAMESPACE)"
	-$(KUBECTL) -n $(K8S_NAMESPACE) scale deployment/api --replicas=0
	-$(KUBECTL) -n $(K8S_NAMESPACE) scale statefulset/worker --replicas=0
	-$(KUBECTL) -n $(K8S_NAMESPACE) delete pvc backtest-results backtest-cache --ignore-not-found
	-$(KUBECTL) -n backtest-workflows delete pvc backtest-results backtest-cache --ignore-not-found
	$(MAKE) k3s-apply-host-volumes
	$(KUBECTL) apply -k $(K8S_LOCAL_OVERLAY)
	$(KUBECTL) -n $(K8S_NAMESPACE) scale deployment/api --replicas=1
	$(KUBECTL) -n $(K8S_NAMESPACE) scale statefulset/worker --replicas=1
	$(MAKE) k8s-restart-workloads

k3s-deploy: ## Apply local kustomize overlay, hostPath PVs, and sync ALPACA_* from local env into app-secrets
	$(MAKE) k3s-apply-host-volumes
	-$(KUBECTL) -n $(K8S_NAMESPACE) delete job/migrate --ignore-not-found
	$(KUBECTL) apply -k $(K8S_LOCAL_OVERLAY)
	$(MAKE) sync-app-secrets
	$(MAKE) k8s-restart-workloads

open-results: ## Open HOST_BACKTEST_RESULTS in Finder (macOS)
	@mkdir -p "$(HOST_BACKTEST_RESULTS)"
	@open "$(HOST_BACKTEST_RESULTS)"

k8s-workflows-deploy: ## Apply Argo workflow manifests under deploy/k8s/workflows
	$(KUBECTL) apply -k deploy/k8s/workflows

k8s-workflows-deploy-local: ## Apply workflow manifests with RWO PVCs for Rancher Desktop / local-path
	$(KUBECTL) apply -k deploy/k8s/overlays/local-workflows
	$(MAKE) k8s-restart-workloads

bootstrap-backtest-workflows-namespace: ## Bootstrap backtest-workflows namespace (scripts/bootstrap_backtest_workflows_namespace.sh)
	chmod +x scripts/bootstrap_backtest_workflows_namespace.sh
	K8S_CONTEXT="$(K8S_CONTEXT)" ./scripts/bootstrap_backtest_workflows_namespace.sh

sync-app-secrets: ## Push ALPACA_* from local env into cluster secrets (backtest + backtest-workflows)
	chmod +x scripts/sync_app_secrets_from_env.sh
	K8S_CONTEXT="$(K8S_CONTEXT)" ./scripts/sync_app_secrets_from_env.sh

test-argo-inline: ## Run the inline Argo workflow smoke test (scripts/test_argo_inline.sh)
	./scripts/test_argo_inline.sh | jq

api-port-forwards: ## Start postgres/redis/argo port-forwards in a tmux session (api-serve prerequisite)
	chmod +x scripts/api_port_forwards_tmux.sh
	K8S_CONTEXT="$(K8S_CONTEXT)" \
	K8S_NAMESPACE="$(K8S_NAMESPACE)" \
	API_PORT_FORWARDS_SESSION="$(API_PORT_FORWARDS_SESSION)" \
	POSTGRES_LOCAL_PORT="$(POSTGRES_LOCAL_PORT)" \
	REDIS_LOCAL_PORT="$(REDIS_LOCAL_PORT)" \
	ARGO_SERVER_PORT="$(ARGO_SERVER_PORT)" \
	POSTGRES_SERVICE_PORT="$(POSTGRES_SERVICE_PORT)" \
	REDIS_SERVICE_PORT="$(REDIS_SERVICE_PORT)" \
	ARGO_SERVER_SERVICE_PORT="$(ARGO_SERVER_SERVICE_PORT)" \
	ARGO_K8S_NAMESPACE="$(ARGO_K8S_NAMESPACE)" \
	ARGO_SERVER_SERVICE_NAME="$(ARGO_SERVER_SERVICE_NAME)" \
	./scripts/api_port_forwards_tmux.sh

api-port-forwards-stop: ## Stop the tmux session started by api-port-forwards
	@if tmux has-session -t "$(API_PORT_FORWARDS_SESSION)" 2>/dev/null; then \
		tmux kill-session -t "$(API_PORT_FORWARDS_SESSION)"; \
		printf 'Stopped tmux session %s\n' "$(API_PORT_FORWARDS_SESSION)"; \
	else \
		printf 'No tmux session named %s\n' "$(API_PORT_FORWARDS_SESSION)"; \
	fi

api-serve: ## Run the Python API on the host (Argo Workflows in local k3s/docker)
	@set -e; \
	. ./scripts/source_env_preserve_exports.sh ./.env; \
	export PYTHONPATH="$${PYTHONPATH:-$(CURDIR)/src}"; \
	export DATABASE_URL="$${DATABASE_URL:-$(API_DATABASE_URL)}"; \
	case "$$DATABASE_URL" in *@postgres:*) export DATABASE_URL="$(API_DATABASE_URL)";; esac; \
	export REDIS_URL="$${REDIS_URL:-$(API_REDIS_URL)}"; \
	case "$$REDIS_URL" in redis://redis:*) export REDIS_URL="$(API_REDIS_URL)";; esac; \
	export BACKTEST_ARGO_ENABLED="$${BACKTEST_ARGO_ENABLED:-true}"; \
	export ARGO_NAMESPACE="$${ARGO_NAMESPACE:-$(ARGO_NAMESPACE)}"; \
	export ARGO_WORKFLOW_SERVICE_ACCOUNT="$${ARGO_WORKFLOW_SERVICE_ACCOUNT:-$(ARGO_WORKFLOW_SERVICE_ACCOUNT)}"; \
	export BACKTEST_RESULTS_DIR="$${BACKTEST_RESULTS_DIR:-$(API_RESULTS_DIR)}"; \
	export BACKTEST_CACHE_DIR="$${BACKTEST_CACHE_DIR:-$(API_CACHE_DIR)}"; \
	export API_HOST="$(API_HOST)"; \
	export API_PORT="$(API_PORT)"; \
	export K8S_CONTEXT="$(K8S_CONTEXT)"; \
	export K8S_NAMESPACE="$(K8S_NAMESPACE)"; \
	export API_PORT_FORWARDS_SESSION="$(API_PORT_FORWARDS_SESSION)"; \
	export POSTGRES_LOCAL_PORT="$(POSTGRES_LOCAL_PORT)"; \
	export REDIS_LOCAL_PORT="$(REDIS_LOCAL_PORT)"; \
	export ARGO_SERVER_PORT="$(ARGO_SERVER_PORT)"; \
	export ARGO_SERVER_URL="$${ARGO_SERVER_URL:-$(ARGO_SERVER_URL)}"; \
	check_tcp() { (echo >/dev/tcp/localhost/$(POSTGRES_LOCAL_PORT)) >/dev/null 2>&1; }; \
	if ! check_tcp; then \
		echo "Postgres port-forward on localhost:$(POSTGRES_LOCAL_PORT) is not reachable; starting api-port-forwards..."; \
		$(MAKE) api-port-forwards; \
		i=0; \
		until check_tcp || [ $$i -ge 20 ]; do \
			i=$$((i + 1)); \
			sleep 1; \
		done; \
	fi; \
	if ! check_tcp; then \
		echo "Postgres is still unreachable on localhost:$(POSTGRES_LOCAL_PORT). Run 'make api-port-forwards' and try again." >&2; \
		exit 1; \
	fi; \
	alembic upgrade head; \
	chmod +x scripts/print_api_serve_prerequisites.sh; \
	./scripts/print_api_serve_prerequisites.sh; \
	if command -v kalyxctl >/dev/null 2>&1; then \
		exec kalyxctl serve --host "$(API_HOST)" --port "$(API_PORT)"; \
	else \
		exec python -m app.cli serve --host "$(API_HOST)" --port "$(API_PORT)"; \
	fi
