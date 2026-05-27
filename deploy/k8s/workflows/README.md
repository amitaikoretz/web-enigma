# Backtest workflow namespace

Argo backtest workflows run in the **`backtest-workflows`** namespace under service account **`backtest-workflow`**.

This bundle is separate from the main app stack (`namespace/backtest`) so you can deploy workflow runtime resources once and submit from the local API via Argo Server HTTP or from the in-cluster API.

## Deploy

For **Rancher Desktop / kind / minikube** (storage class `local-path` only supports `ReadWriteOnce`):

```bash
make k8s-workflows-deploy-local
# or: kubectl apply -k deploy/k8s/overlays/local-workflows
```

For clusters with a `ReadWriteMany` storage class:

```bash
kubectl apply -k deploy/k8s/workflows
```

Or from the repo root:

```bash
make k8s-workflows-deploy
```

Verify:

```bash
kubectl -n backtest-workflows get sa,role,rolebinding,pvc
kubectl auth can-i create workflowtaskresults.argoproj.io \
  --as=system:serviceaccount:backtest-workflows:backtest-workflow \
  -n backtest-workflows
```

The workflow service account needs `create`/`patch` on `workflowtaskresults` so Argo's wait sidecar can report task completion. Without it, steps fail with `exit code 64` and a forbidden error on `workflowtaskresults.argoproj.io`.

The `plan-shards` step writes its `withParam` output to `/tmp/shards-param.json` (not on the workspace PVC). Argo's emissary executor cannot collect output parameters from workflow volume mounts reliably. The step also writes `manifest-path` and `work-dir` to `/tmp/manifest-path.txt` and `/tmp/work-dir.txt` for downstream merge wiring.

The first workflow step, `print-payload`, logs a copy-pasteable `curl` command for `POST /backtests/argo` using the workflow parameters. Override the API target when port-forwarding locally:

```bash
argo submit -n backtest-workflows --from workflowtemplate/backtest-batch \
  -p api-base-url=http://localhost:8000 \
  -p config-path=/data/backtest-results/my-experiment/my-experiment.yaml \
  -p output-path=/data/backtest-results/my-experiment/my-experiment.json \
  -p split-by=symbol \
  -p backtest-id=my-experiment
```

When launching via the API, the config YAML is embedded in the workflow as a base64 parameter so the plan step does not depend on the API pod's PVC being the same volume as `backtest-workflows`. For manual `argo submit --from workflowtemplate/backtest-batch`, either copy the config onto the workflow namespace `backtest-results` PVC at `config-path`, or pass `-p config-b64=$(base64 -w0 < config.yaml)` (GNU base64; on macOS omit `-w0`).

## Credentials secret

Workflow pods mount `app-secrets` for Alpaca credentials. Sync from your local shell or `.env` (same as the main app stack):

```bash
export ALPACA_API_KEY='your-key'
export ALPACA_SECRET_KEY='your-secret'
make sync-app-secrets
```

This updates `app-secrets` in **`backtest`** and copies it into **`backtest-workflows`**. New workflow pods pick up the secret immediately; re-submit workflows that were already running before the sync.

If you only need a manual copy from an existing `backtest` secret:

```bash
kubectl get secret app-secrets -n backtest -o yaml \
  | sed '/resourceVersion:/d;/uid:/d;/creationTimestamp:/d' \
  | sed 's/namespace: backtest/namespace: backtest-workflows/' \
  | kubectl apply -f -
```

## Database access

Workflow pods mount the same `app-secrets` as the main stack, including `DATABASE_URL` with host `postgres`. That short name only resolves inside the **`backtest`** namespace where the Postgres Deployment runs.

This bundle adds an **ExternalName** Service `postgres` in **`backtest-workflows`** that points at `postgres.backtest.svc.cluster.local`, so steps such as `merge-reports` (which update job metadata in Postgres) can connect without changing the secret.

Verify after deploy:

```bash
kubectl get svc postgres -n backtest-workflows
```

**Staging / production:** If `DATABASE_URL` uses a managed host (not `@postgres:`), behavior is unchanged. If Postgres lives in another in-cluster namespace, patch `spec.externalName` on `service-postgres-external.yaml` via a workflows overlay.

## API configuration

Point the API at this namespace and service account:

```bash
export ARGO_NAMESPACE=backtest-workflows
export ARGO_WORKFLOW_SERVICE_ACCOUNT=backtest-workflow
```

These are the defaults in code and in `deploy/k8s/base/configmap-backtest.yaml` for the in-cluster API.

## Argo Server access

If you submit via `ARGO_SERVER_URL`, the Argo Server service account must be allowed to create workflows and pods in `backtest-workflows`. Many installs use a cluster-scoped role; namespace-scoped installs may need an extra RoleBinding for the Argo Server SA (often `argo-server` in namespace `argo`).

## Shared storage note

Workflow pods read config/output paths on `/data/backtest-results` backed by the `backtest-results` PVC in **`backtest-workflows`**. Config files written by a local API on your laptop are not visible to cluster workflows unless you copy them onto that volume or use a shared filesystem.
