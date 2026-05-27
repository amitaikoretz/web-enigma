# Kubernetes Deployment

Kustomize manifests for running the same application stack as [`docker-compose.yml`](../../docker-compose.yml).

For architecture and future production behaviors (market-hours scaling, drain hooks, managed services), see [`docs/k8s-trading-agent-design.md`](../../docs/k8s-trading-agent-design.md).

## Layout

```text
deploy/k8s/
  base/                 Shared Deployments, Services, ConfigMap, migrate Job
  overlays/local/       In-cluster Postgres + Redis for dev/kind/minikube
  overlays/staging/     Base only — bring your own secrets and managed data stores
```

## Components

| Resource | Compose equivalent | Notes |
|----------|-------------------|-------|
| `Job/migrate` | `migrate` | One-shot Alembic upgrade (API also runs migrate on startup) |
| `Deployment/api` | `api` | FastAPI on port 8000 |
| `Deployment/controller` | `controller` | Live contracts controller |
| `StatefulSet/worker` | `worker-0`, `worker-1` | Shard id from pod name (`worker-0` → `--shard-id 0`) |
| `CronJob/reconciler` | `reconciler` | Suspended by default; enable when ready |
| `CronJob/backtest-reconciler` | — | Syncs Argo workflow status into backtest job metadata |
| `WorkflowTemplate/backtest-batch` | — | Parallel backtest fan-out (plan → run → merge) |
| `PVC/backtest-results`, `PVC/backtest-cache` | — | Shared results and parquet cache for API + workflow pods |

## Prerequisites

- Kubernetes 1.27+ with `kubectl`
- Container images built locally or pushed to a registry
- Alpaca API credentials for live runtime paths

## Build images

From the repo root:

```bash
docker build -t backtest-app:latest .
docker build -t backtest-web:latest -f web/Dockerfile web/
```

### Rancher Desktop (recommended)

Rancher Desktop k3s reads images from the **containerd `k8s.io` namespace**, not from regular `docker images`. Build and deploy from the repo root:

```bash
make k8s-local-images    # nerdctl --namespace k8s.io build + pull deps
make k3s-deploy
```

If Kubernetes is set to the **Moby (dockerd)** runtime in Rancher Desktop preferences:

```bash
make K8S_BUILD=docker k8s-local-images
make k3s-deploy
```

Without `k8s-local-images`, `api` stays in `Init:ImagePullBackOff` (kubelet tries `docker.io/library/backtest-app:latest`), and `web` stays in `Init:0/1` waiting for the API.

Confirm images exist in k3s:

```bash
nerdctl --namespace k8s.io images | grep backtest
```

### kind / minikube

Load images into the cluster after building:

```bash
kind load docker-image backtest-app:latest backtest-web:latest
# or: minikube image load backtest-app:latest backtest-web:latest
```

Override image names/tags in `overlays/local/kustomization.yaml` or `overlays/staging/kustomization.yaml` when using a registry.

## Local overlay (full stack)

The local overlay starts Postgres, Redis, API, controller, two worker shards, and the web UI.

1. **Rancher Desktop:** run `make k8s-local-images` before apply (see above).

2. Set Alpaca credentials from your local environment (not in kustomize manifests):

```bash
export ALPACA_API_KEY='your-key'
export ALPACA_SECRET_KEY='your-secret'
# or populate repo-root .env (see .env.example)

make sync-app-secrets
```

Run after deploy whenever credentials change or after a fresh cluster setup:

```bash
make k3s-deploy sync-app-secrets
```

3. Render and inspect:

```bash
kubectl kustomize deploy/k8s/overlays/local
```

4. Deploy (if you skipped `make k3s-deploy`):

```bash
kubectl apply -k deploy/k8s/overlays/local
```

5. Wait for core services:

```bash
kubectl -n backtest wait --for=condition=available deployment/postgres --timeout=120s
kubectl -n backtest wait --for=condition=available deployment/redis --timeout=120s
kubectl -n backtest wait --for=condition=available deployment/api --timeout=180s
kubectl -n backtest wait --for=condition=ready pod -l app.kubernetes.io/name=worker --timeout=180s
```

6. Port-forward the API (or web):

```bash
kubectl -n backtest port-forward svc/api 8000:8000
curl http://localhost:8000/health
```

Web UI:

```bash
kubectl -n backtest port-forward svc/web 8080:80
```

Open http://localhost:8080

### Local ingress (Rancher Desktop / k3s)

The local overlay includes an Ingress for Traefik (default on Rancher Desktop k3s). Nginx in the web pod proxies `/api/` to the API Service, so one hostname serves UI and API.

1. Deploy (or re-apply) the local overlay:

```bash
kubectl apply -k deploy/k8s/overlays/local
```

2. Confirm the web pod has endpoints (init waits for API health):

```bash
kubectl -n backtest get endpoints web
kubectl -n backtest get pods -l app.kubernetes.io/name=web
```

3. Open one of these URLs (do **not** use bare `http://localhost` — Traefik routes by hostname):

- http://backtest.127.0.0.1.sslip.io (no `/etc/hosts` needed)
- http://backtest.local (add `127.0.0.1 backtest.local` to `/etc/hosts` if it does not resolve)

Verify:

```bash
curl -v http://backtest.127.0.0.1.sslip.io/
kubectl -n backtest get ingress web
kubectl -n backtest describe ingress web
```

**Traefik returns `404 page not found`**

- Wrong URL: use a hostname from the Ingress rule, not `http://127.0.0.1/` alone.
- Ingress ignored: `kubectl get ingressclass` — if only `nginx` exists, Traefik is disabled. Add [`patch-ingress-nginx-class.yaml`](overlays/local/patch-ingress-nginx-class.yaml) under `patches:` in `kustomization.yaml`, re-apply, then use the [NGINX ingress port-forward flow](https://docs.rancherdesktop.io/how-to-guides/setup-NGINX-Ingress-Controller/) or your controller’s external IP.
- Empty backend: `kubectl -n backtest get endpoints web` must list pod IPs; fix API/web image pulls (`make k8s-local-images`) if pods are not ready.

Change hostnames in [`overlays/local/ingress-web.yaml`](overlays/local/ingress-web.yaml) if you prefer another name.

6. Seed a sample trading contract (API must be reachable):

```bash
kubectl -n backtest port-forward svc/api 8000:8000 &
API_BASE_URL=http://localhost:8000 ./examples/live/seed_contracts.sh
```

## Staging / production overlay

`overlays/staging` applies the application workloads without in-cluster Postgres or Redis.

1. Create secrets before or after namespace creation:

```bash
kubectl create namespace backtest
kubectl create secret generic app-secrets -n backtest \
  --from-literal=DATABASE_URL='postgresql+psycopg://user:pass@host:5432/backtest' \
  --from-literal=ALPACA_API_KEY='your-key' \
  --from-literal=ALPACA_SECRET_KEY='your-secret'
```

2. Patch image references and external Redis URL in:
   - `overlays/staging/kustomization.yaml` (`images`)
   - `base/configmap-live.yaml` (`global_config.redis.url`)
   - `base/deployment-api.yaml` (`REDIS_URL`, `LIVE_REDIS_URL`)

3. Deploy:

```bash
kubectl apply -k deploy/k8s/overlays/staging
```

Use a managed Postgres instance and Redis/ElastiCache in production rather than the local overlay data stores.

## Startup order

Kubernetes applies resources concurrently. Ordering is handled by:

1. **Postgres / Redis** — readiness probes (local overlay)
2. **API** — init container runs `alembic upgrade head` after DB is reachable
3. **Controller / workers / web** — init containers wait for `GET /health` on the API Service
4. **Workers** — StatefulSet pod names supply stable shard ids

The standalone `migrate` Job remains useful for CI and explicit pre-deploy migration runs:

```bash
kubectl -n backtest delete job migrate --ignore-not-found
kubectl apply -k deploy/k8s/overlays/local
kubectl -n backtest wait --for=condition=complete job/migrate --timeout=180s
```

## Optional: reconciler CronJob

The reconciler is suspended by default (`spec.suspend: true`). Enable it when you want periodic reconciliation:

```bash
kubectl -n backtest patch cronjob reconciler -p '{"spec":{"suspend":false}}'
```

Run once manually:

```bash
kubectl -n backtest create job --from=cronjob/reconciler reconciler-manual-$(date +%s)
```

## Health checklist

After deploy:

1. API: `kubectl -n backtest exec deploy/api -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"`
2. Redis: `kubectl -n backtest exec deploy/redis -- redis-cli ping`
3. Postgres: `kubectl -n backtest exec deploy/postgres -- pg_isready -U postgres -d backtest`
4. Workers: `kubectl -n backtest get pods -l app.kubernetes.io/name=worker`

## Configuration

- Live runtime YAML: `ConfigMap/live-config` (mounted at `/app/config/live.yaml`)
- Credentials and `DATABASE_URL`: `Secret/app-secrets` — local dev: `make sync-app-secrets` (reads `ALPACA_*` from your shell or `.env`)
- Template for manual secret creation: [`base/secret.example.yaml`](base/secret.example.yaml)

Worker shard count must stay aligned across:

- `configmap-live.yaml` → `global_config.controller.shard_count`
- `deployment-api.yaml` → `LIVE_SHARD_COUNT`
- `statefulset-workers.yaml` → `spec.replicas`

## Argo backtest workflows

The cluster must have [Argo Workflows](https://argo-workflows.readthedocs.io/en/latest/operator-manual/installation/) installed separately. Backtest workflows run in namespace **`backtest-workflows`** under service account **`backtest-workflow`**.

### Deploy workflow namespace

```bash
make bootstrap-backtest-workflows-namespace
# or: kubectl apply -k deploy/k8s/workflows
```

See [`workflows/README.md`](workflows/README.md) for secrets, PVCs, and Argo Server RBAC notes.

### Prerequisites

- Argo Workflows controller running in the cluster
- `ReadWriteMany` storage class for `backtest-results` and `backtest-cache` PVCs in `backtest-workflows`
- `app-secrets` in `backtest-workflows` when configs use Alpaca data

### Launch options

1. **API** — `POST /backtests/argo` with `config_path` (on the shared volume) or inline `config_text`
2. **Wizard** — enable **Argo Workflows** in platform settings (`POST /backtests` delegates to Argo when enabled)
3. **CLI / Argo** — submit the bundled template (optional; the API submits inline workflows):

```bash
argo submit -n backtest-workflows --from workflowtemplate/backtest-batch \
  -p config-path=/data/backtest-results/my-experiment.yaml \
  -p output-path=/data/backtest-results/my-experiment.json \
  -p split-by=symbol \
  -p backtest-id=my-experiment
```

Shard planning and merge use `backtest plan-shards` and `backtest merge` inside the workflow.

### Enable status reconciliation

```bash
kubectl -n backtest patch cronjob backtest-reconciler -p '{"spec":{"suspend":false}}'
```

The reconciler runs `backtest argo-reconciler --once` to sync Argo workflow phase into the `backtest_jobs` table the UI polls.

### Status and progress API

`GET /backtests/{id}/status` returns job status plus `progress_pct` (0–100) and `is_terminal`. The API refreshes Argo workflow state on each status request and computes run-level progress from shard reports under `{backtest_id}/` on the shared `backtest-results` PVC. The web UI polls this endpoint until `is_terminal` is true. The optional `backtest-reconciler` CronJob remains a backup when the API is not polling.

## Teardown

```bash
kubectl delete -k deploy/k8s/overlays/local
```

## Related docs

- [Docker Compose Guide](../../docs/docker-compose.md)
- [Live Runtime Guide](../../docs/live-runtime.md)
- [Kubernetes Design Notes](../../docs/k8s-trading-agent-design.md)
