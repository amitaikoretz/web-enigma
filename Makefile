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
ifeq ($(K8S_BUILD),nerdctl)
  K8S_CLI := nerdctl --namespace k8s.io
else
  K8S_CLI := docker
endif

.DEFAULT_GOAL := help

.PHONY: help k8s-local-images build-k8s-app build-k8s-web pull-k8s-deps k3s-deploy k8s-restart-workloads k8s-workflows-deploy k8s-workflows-deploy-local test-argo-inline bootstrap-backtest-workflows-namespace

help: ## List available targets (default)
	@printf '\n'
	@printf '  %-32s  %s\n' 'Target' 'Description'
	@printf '  %-32s  %s\n' '------' '-----------'
	@grep -hE '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  %-32s  %s\n", $$1, $$2}' \
		| sort
	@printf '\n'
	@printf '  Variables: K8S_BUILD=%s  K8S_NAMESPACE=%s  K8S_LOCAL_OVERLAY=%s\n' \
		'$(K8S_BUILD)' '$(K8S_NAMESPACE)' '$(K8S_LOCAL_OVERLAY)'
	@printf '             APP_IMAGE=%s  WEB_IMAGE=%s\n\n' '$(APP_IMAGE)' '$(WEB_IMAGE)'

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
	kubectl -n $(K8S_NAMESPACE) rollout restart deployment/api deployment/controller deployment/web statefulset/worker
	kubectl -n $(K8S_NAMESPACE) rollout status deployment/api --timeout=180s
	kubectl -n $(K8S_NAMESPACE) rollout status deployment/controller --timeout=180s
	kubectl -n $(K8S_NAMESPACE) rollout status deployment/web --timeout=180s
	kubectl -n $(K8S_NAMESPACE) rollout status statefulset/worker --timeout=240s

k3s-deploy: ## Apply local kustomize overlay and restart workloads
	kubectl apply -k $(K8S_LOCAL_OVERLAY)
	$(MAKE) k8s-restart-workloads

k8s-workflows-deploy: ## Apply Argo workflow manifests under deploy/k8s/workflows
	kubectl apply -k deploy/k8s/workflows

k8s-workflows-deploy-local: ## Apply workflow manifests with RWO PVCs for Rancher Desktop / local-path
	kubectl apply -k deploy/k8s/overlays/local-workflows
	$(MAKE) k8s-restart-workloads

bootstrap-backtest-workflows-namespace: ## Bootstrap backtest-workflows namespace (scripts/bootstrap_backtest_workflows_namespace.sh)
	chmod +x scripts/bootstrap_backtest_workflows_namespace.sh
	./scripts/bootstrap_backtest_workflows_namespace.sh

test-argo-inline: ## Run the inline Argo workflow smoke test (scripts/test_argo_inline.sh)
	./scripts/test_argo_inline.sh | jq
