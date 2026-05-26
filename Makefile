# Local k3s image names (see deploy/k8s/base/kustomization.yaml)
APP_IMAGE ?= backtest-app:latest
WEB_IMAGE ?= backtest-web:latest

# Third-party images referenced by deploy/k8s/overlays/local
K8S_DEP_IMAGES ?= postgres:16-alpine redis:7-alpine busybox:1.36

# Rancher Desktop k3s reads images from the containerd k8s.io namespace.
# Use `make K8S_BUILD=docker k8s-local-images` when RD is set to the Moby (dockerd) runtime.
K8S_BUILD ?= nerdctl
K8S_LOCAL_OVERLAY ?= deploy/k8s/overlays/local
ifeq ($(K8S_BUILD),nerdctl)
  K8S_CLI := nerdctl --namespace k8s.io
else
  K8S_CLI := docker
endif

.PHONY: k8s-local-images build-k8s-app build-k8s-web pull-k8s-deps

k8s-local-images: build-k8s-app build-k8s-web pull-k8s-deps
	@echo ""
	@echo "Deploy with:"
	@echo "  kubectl apply -k $(K8S_LOCAL_OVERLAY)"

build-k8s-app:
	$(K8S_CLI) build -t $(APP_IMAGE) .

build-k8s-web:
	$(K8S_CLI) build -t $(WEB_IMAGE) -f web/Dockerfile web/

pull-k8s-deps:
	@for img in $(K8S_DEP_IMAGES); do \
		echo "Pulling $$img"; \
		$(K8S_CLI) pull $$img; \
	done
