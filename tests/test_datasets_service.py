from __future__ import annotations

from datetime import date, datetime, UTC
from pathlib import Path

import pandas as pd

from app.datasets.argo_workflow import build_dataset_workflow_spec
from app.datasets.models import DatasetListItem
from app.datasets.service import DatasetService
from app.datasets.sharding import build_dataset_shard_plan, write_json_file
from app.settings.service import PlatformSettingsService


class FakeDatasetRepository:
    def __init__(self, item: DatasetListItem):
        self.item = item
        self.updated: list[DatasetListItem] = []

    def get(self, dataset_id: str) -> DatasetListItem | None:
        return self.item if dataset_id == self.item.id else None

    def update(self, item: DatasetListItem) -> None:
        self.item = item
        self.updated.append(item)

    def create(self, item: DatasetListItem) -> None:  # pragma: no cover - unused in test
        self.item = item

    def delete_artifacts(self, item: DatasetListItem) -> None:  # pragma: no cover - unused in test
        return None

    def delete(self, dataset_id: str) -> DatasetListItem | None:  # pragma: no cover - unused in test
        if dataset_id != self.item.id:
            return None
        deleted = self.item
        self.item = None  # type: ignore[assignment]
        return deleted

    def list_recent(self, *, limit: int = 100) -> list[DatasetListItem]:  # pragma: no cover - unused
        return [self.item] if self.item is not None else []


class FakeSettingsService:
    def __init__(self, dataset_storage_root: str = "/tmp/datasets") -> None:
        self.dataset_storage_root = dataset_storage_root

    def load(self):  # pragma: no cover - simple test stub
        return type(
            "Settings",
            (),
            {"backtest_defaults": type("Defaults", (), {"dataset_storage_root": self.dataset_storage_root})()},
        )()


class FakeArgoSubmitter:
    def __init__(self, workflow: dict[str, object] | None = None):
        self.workflow = workflow
        self.config = type("Config", (), {"namespace": "default"})()

    @property
    def is_configured(self) -> bool:
        return True

    def get_workflow(self, workflow_name: str, *, namespace: str | None = None):
        return self.workflow

    def get_workflow_phase(self, workflow_name: str, *, namespace: str | None = None):
        workflow = self.get_workflow(workflow_name, namespace=namespace)
        if not workflow:
            return None
        status = workflow.get("status")
        if not isinstance(status, dict):
            return None
        phase = status.get("phase")
        return phase if isinstance(phase, str) else None


class CaptureArgoSubmitter(FakeArgoSubmitter):
    def __init__(self) -> None:
        super().__init__(workflow=None)
        self.submitted: dict[str, object] | None = None

    def _http_request(self, method: str, path: str, *, endpoint_name: str, json: dict[str, object]):
        self.submitted = {"method": method, "path": path, "endpoint_name": endpoint_name, "json": json}
        return type("Response", (), {"status_code": 200, "text": ""})()


def _dataset_item() -> DatasetListItem:
    return DatasetListItem(
        id="ds-1",
        name="My dataset",
        symbol="AAPL",
        symbols=["AAPL"],
        provider="alpaca",
        resolution="1d",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 1),
        created_at=datetime(2026, 6, 7, tzinfo=UTC),
        updated_at=datetime(2026, 6, 7, tzinfo=UTC),
        status="running",
        argo_namespace="default",
        argo_workflow_name="dataset-ds-1",
        params_json={
            "symbol": "AAPL",
            "symbols": ["AAPL"],
            "provider": "alpaca",
            "resolution": "1d",
            "start_date": "2026-05-01",
            "end_date": "2026-06-01",
            "name": "My dataset",
            "options": {"enabled": False, "feed": "indicative"},
        },
        output_dir="/tmp/datasets",
        dataset_parquet_path=None,
        manifest_path=None,
        error_message=None,
        progress_pct=0.0,
    )


def test_refresh_from_argo_persists_workflow_output_paths(tmp_path: Path) -> None:
    item = _dataset_item()
    repo = FakeDatasetRepository(item)
    workflow = {
        "status": {
            "phase": "Succeeded",
            "outputs": {
                "parameters": [
                    {"name": "dataset-path", "value": str(tmp_path / "aapl.parquet")},
                    {"name": "manifest-path", "value": str(tmp_path / "aapl.manifest.json")},
                ]
            },
        }
    }
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter(workflow))

    service._refresh_from_argo(item, write_back=True)

    assert repo.item.status == "completed"
    assert repo.item.dataset_parquet_path == str(tmp_path / "aapl.parquet")
    assert repo.item.manifest_path == str(tmp_path / "aapl.manifest.json")
    assert repo.updated


def test_get_dataset_parquet_path_falls_back_to_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "datasets"
    parquet_path = output_dir / "ds-1" / "AAPL-alpaca-1d.parquet"
    parquet_path.parent.mkdir(parents=True)
    parquet_path.write_text("data", encoding="utf-8")
    item = _dataset_item().model_copy(
        update={
            "status": "completed",
            "dataset_parquet_path": None,
            "output_dir": str(output_dir),
        }
    )
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter())

    assert service.get_dataset_parquet_path("ds-1") == parquet_path


def test_get_dataset_parquet_path_translates_workflow_mount_to_host_mirror(tmp_path: Path, monkeypatch) -> None:
    host_root = tmp_path / "host-datasets"
    host_root.mkdir()
    workflow_root = tmp_path / "workflow-results"
    workflow_root.mkdir()
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(workflow_root))

    workflow_path = workflow_root / "AAPL-alpaca-1d.parquet"
    host_path = host_root / "AAPL-alpaca-1d.parquet"
    host_path.write_text("data", encoding="utf-8")

    item = _dataset_item().model_copy(
        update={
            "status": "completed",
            "dataset_parquet_path": str(workflow_path),
            "output_dir": str(host_root),
        }
    )
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter())

    assert service.get_dataset_parquet_path("ds-1") == host_path


def test_list_datasets_hydrates_artifact_paths_from_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "datasets"
    dataset_dir = output_dir / "ds-1"
    dataset_dir.mkdir(parents=True)
    parquet_path = dataset_dir / "AAPL-alpaca-1d.parquet"
    manifest_path = dataset_dir / "AAPL-alpaca-1d.manifest.json"
    parquet_path.write_text("data", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    item = _dataset_item().model_copy(
        update={
            "status": "completed",
            "dataset_parquet_path": None,
            "manifest_path": None,
            "output_dir": str(output_dir),
        }
    )
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter())

    response = service.list_datasets()

    assert response.items[0].dataset_parquet_path == str(parquet_path)
    assert response.items[0].manifest_path == str(manifest_path)
    assert repo.item.dataset_parquet_path == str(parquet_path)
    assert repo.item.manifest_path == str(manifest_path)


def test_get_detail_includes_symbol_options_from_dataset_parquet(tmp_path: Path) -> None:
    parquet_path = tmp_path / "AAPL-alpaca-1d.parquet"
    pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT", "AAPL"],
            "timestamp": ["2026-06-01T00:00:00Z", "2026-06-01T00:01:00Z", "2026-06-01T00:02:00Z"],
        }
    ).to_parquet(parquet_path, index=False)

    item = _dataset_item().model_copy(
        update={
            "status": "completed",
            "dataset_parquet_path": str(parquet_path),
        }
    )
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter())

    detail = service.get_detail("ds-1")

    assert detail is not None
    assert detail.symbol_options == ["AAPL", "MSFT"]


def test_get_detail_falls_back_to_recorded_symbol_when_symbol_column_missing(tmp_path: Path) -> None:
    parquet_path = tmp_path / "AAPL-alpaca-1d.parquet"
    pd.DataFrame(
        {
            "timestamp": ["2026-06-01T00:00:00Z"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [100.0],
        }
    ).to_parquet(parquet_path, index=False)

    item = _dataset_item().model_copy(
        update={
            "status": "completed",
            "dataset_parquet_path": str(parquet_path),
        }
    )
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter())

    detail = service.get_detail("ds-1")

    assert detail is not None
    assert detail.symbol_options == ["AAPL"]


def test_dataset_workflow_spec_mounts_shared_results(monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", "/data/backtest-results")

    spec = build_dataset_workflow_spec(
        symbols=["AAPL", "MSFT"],
        provider="alpaca",
        resolution="5m",
        start_date="2026-01-01",
        end_date="2026-01-31",
        options_enabled=False,
        options_feed="indicative",
        output_dir="/data/backtest-results",
        options_enabled_flag="--no-options-enabled",
    )

    assert spec["volumes"] == [
        {
            "name": "datasets-results",
            "persistentVolumeClaim": {"claimName": "backtest-results"},
        }
    ]
    assert spec["parallelism"] == 4
    main_template = next(template for template in spec["templates"] if template["name"] == "main")
    step_names = [step["name"] for group in main_template["steps"] for step in group]
    assert step_names == ["print-payload", "plan", "download-shards", "combine"]

    print_payload = next(template for template in spec["templates"] if template["name"] == "print-payload")
    print_mounts = print_payload["container"]["volumeMounts"]
    assert print_mounts == [{"name": "datasets-results", "mountPath": "/data/backtest-results"}]
    print_args = print_payload["container"]["args"]
    assert "__COMMAND_LINE__" not in print_args
    assert "--command-line" in print_args

    plan = next(template for template in spec["templates"] if template["name"] == "plan-shards")
    plan_mounts = plan["container"]["volumeMounts"]
    assert plan_mounts == [{"name": "datasets-results", "mountPath": "/data/backtest-results"}]
    assert plan["retryStrategy"] == {
        "limit": 3,
        "retryPolicy": "Always",
        "backoff": {"duration": "10s", "factor": 2, "maxDuration": "1m"},
    }
    pod_spec_patch = plan["podSpecPatch"]
    assert "asInt(retries)" in pod_spec_patch
    assert "4Gi" in pod_spec_patch
    assert "32Gi" in pod_spec_patch
    plan_args = plan["container"]["args"]
    assert "plan-shards" in plan_args
    assert "--symbol" in plan_args
    assert "{{inputs.parameters.symbols}}" in plan_args
    assert "--shards-param-out" in plan_args
    assert "/tmp/shards-param.json" in plan_args
    plan_outputs = plan["outputs"]["parameters"]
    plan_output_names = [item["name"] for item in plan_outputs]
    assert plan_output_names == ["plan-path", "work-dir", "shards", "terminal-command", "error-exception", "error-code-location", "error-call-stack", "error-traceback"]

    download = next(template for template in spec["templates"] if template["name"] == "download-shard")
    download_args = download["container"]["args"]
    assert "download-shard" in download_args
    assert "{{inputs.parameters.progress-total-units}}" in download_args
    assert "{{inputs.parameters.progress-symbol-units}}" in download_args
    assert download["retryStrategy"] == plan["retryStrategy"]
    assert download["podSpecPatch"] == plan["podSpecPatch"]
    assert download["metadata"]["annotations"]["workflows.argoproj.io/progress"] == "0/100"

    combine = next(template for template in spec["templates"] if template["name"] == "combine-shards")
    combine_args = combine["container"]["args"]
    assert "combine-shards" in combine_args
    assert "{{inputs.parameters.plan-path}}" in combine_args
    assert "/tmp/manifest-path.txt" in combine_args
    combine_outputs = combine["outputs"]["parameters"]
    combine_output_names = [item["name"] for item in combine_outputs]
    assert combine_output_names == [
        "dataset-path",
        "manifest-path",
        "options-dataset-path",
        "options-manifest-path",
        "terminal-command",
        "error-exception",
        "error-code-location",
        "error-call-stack",
        "error-traceback",
    ]


def test_submit_uses_workflow_mount_in_argo_payload(tmp_path: Path, monkeypatch) -> None:
    host_root = tmp_path / "host-datasets"
    host_root.mkdir()
    workflow_root = tmp_path / "workflow-results"
    workflow_root.mkdir()
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(workflow_root))

    repo = FakeDatasetRepository(_dataset_item())
    service = DatasetService(repo, FakeSettingsService(str(host_root)), argo_submitter=CaptureArgoSubmitter())
    from app.datasets.models import DatasetCreateRequest

    response = service.submit(
        DatasetCreateRequest.model_validate(
            {
                "symbols": ["AAPL", "MSFT"],
                "provider": "alpaca",
                "resolution": "1d",
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 6, 1),
                "name": "My dataset",
            }
        )
    )

    assert response.status == "pending"
    submitted = service.argo.submitted  # type: ignore[attr-defined]
    assert submitted is not None
    workflow = submitted["json"]["workflow"]  # type: ignore[index]
    params = {item["name"]: item["value"] for item in workflow["spec"]["arguments"]["parameters"]}  # type: ignore[index]
    assert params["output-dir"] == str((workflow_root / repo.item.id).resolve())
    assert params["options-enabled-flag"] == "--no-options-enabled"
    assert params["symbols"] == "AAPL,MSFT"


def test_refresh_from_argo_uses_weighted_shard_progress(tmp_path: Path) -> None:
    output_dir = tmp_path / "datasets"
    plan_dir = output_dir / "ds-1"
    plan_dir.mkdir(parents=True, exist_ok=True)
    item = _dataset_item().model_copy(
        update={
            "status": "running",
            "progress_pct": 10.0,
            "argo_namespace": "default",
            "argo_workflow_name": "dataset-ds-1",
            "output_dir": str(output_dir),
        }
    )
    plan = build_dataset_shard_plan(
        dataset_id="ds-1",
        symbols=["AAPL", "MSFT"],
        provider="alpaca",
        resolution="5m",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 1),
        options_enabled=False,
        options_feed="indicative",
        output_dir=plan_dir,
        max_shards=4,
        max_pods=2,
        target_work_units=1_000,
    )
    write_json_file(plan_dir / "shard-plan.json", plan)
    workflow = {
        "status": {
            "phase": "Running",
            "nodes": {
                "node1": {
                    "templateName": "download-shard",
                    "phase": "Running",
                    "progress": "50/100",
                    "inputs": {
                        "parameters": [
                            {"name": "shard-id", "value": plan.shards[0].shard_id},
                            {"name": "output-dir", "value": plan.shards[0].output_dir},
                        ]
                    },
                }
            },
        }
    }
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter(workflow))

    service._refresh_from_argo(item, write_back=True)

    assert repo.item is not None
    assert repo.item.status == "running"
    assert repo.item.progress_pct > 10.0
    assert repo.item.progress_pct < 100.0


def test_refresh_from_argo_marks_terminal_progress_complete(tmp_path: Path) -> None:
    output_dir = tmp_path / "datasets"
    plan_dir = output_dir / "ds-1"
    plan_dir.mkdir(parents=True, exist_ok=True)
    item = _dataset_item().model_copy(
        update={
            "status": "running",
            "progress_pct": 17.0,
            "argo_namespace": "default",
            "argo_workflow_name": "dataset-ds-1",
            "output_dir": str(output_dir),
        }
    )
    plan = build_dataset_shard_plan(
        dataset_id="ds-1",
        symbols=["AAPL"],
        provider="alpaca",
        resolution="1d",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 1),
        options_enabled=False,
        options_feed="indicative",
        output_dir=plan_dir,
        max_shards=4,
        max_pods=2,
        target_work_units=1_000,
    )
    write_json_file(plan_dir / "shard-plan.json", plan)
    workflow = {"status": {"phase": "Succeeded", "nodes": {}}}
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter(workflow))

    service._refresh_from_argo(item, write_back=True)

    assert repo.item is not None
    assert repo.item.status == "completed"
    assert repo.item.progress_pct == 100.0


def test_default_dataset_storage_root_uses_shared_results_mount() -> None:
    from app.settings.models import BacktestDefaults

    assert BacktestDefaults().dataset_storage_root == "/data/datasets"


def test_submit_falls_back_to_api_results_dir_when_dataset_root_is_not_writable(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "api-results" / "settings" / "platform-settings.json"
    repo = FakeDatasetRepository(_dataset_item())
    service = DatasetService(repo, PlatformSettingsService(settings_path), argo_submitter=CaptureArgoSubmitter())
    from app.datasets.models import DatasetCreateRequest

    monkeypatch.setattr(service, "_is_writable_dir", lambda candidate: False)

    response = service.submit(
        DatasetCreateRequest.model_validate(
            {
                "symbols": ["AAPL", "MSFT"],
                "provider": "alpaca",
                "resolution": "1d",
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 6, 1),
                "name": "My dataset",
            }
        )
    )

    assert response.status == "pending"
    assert repo.item.output_dir == str((tmp_path / "api-results").resolve())
    submitted = service.argo.submitted  # type: ignore[attr-defined]
    assert submitted is not None
    workflow = submitted["json"]["workflow"]  # type: ignore[index]
    params = {item["name"]: item["value"] for item in workflow["spec"]["arguments"]["parameters"]}  # type: ignore[index]
    assert params["output-dir"] == str((Path("/data/backtest-results") / repo.item.id).resolve())
    assert params["symbols"] == "AAPL,MSFT"


def test_get_dataset_workflow_errors_returns_argo_error_outputs() -> None:
    item = _dataset_item().model_copy(
        update={
            "status": "failed",
            "argo_namespace": "default",
            "argo_workflow_name": "dataset-ds-1",
        }
    )
    workflow = {
        "status": {
            "phase": "Failed",
            "nodes": {
                "node-1": {
                    "phase": "Failed",
                    "displayName": "main",
                    "templateName": "main",
                    "outputs": {
                        "parameters": [
                            {"name": "error-exception", "value": "RuntimeError: boom"},
                            {"name": "error-code-location", "value": "/tmp/train.py:42"},
                            {"name": "error-call-stack", "value": "/tmp/train.py:42\n/tmp/train.py:13\n"},
                            {"name": "error-traceback", "value": "Traceback (most recent call last):\nboom"},
                        ]
                    },
                }
            },
        }
    }
    repo = FakeDatasetRepository(item)
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=FakeArgoSubmitter(workflow))

    details = service.get_workflow_errors("ds-1")

    assert details is not None
    assert details.dataset_id == "ds-1"
    assert details.available is True
    assert details.error_exception == "RuntimeError: boom"
    assert details.error_code_location == "/tmp/train.py:42"
    assert details.error_call_stack == ["/tmp/train.py:42", "/tmp/train.py:13"]


def test_retry_dataset_submits_a_new_workflow() -> None:
    item = _dataset_item().model_copy(
        update={
            "status": "failed",
            "argo_namespace": "default",
            "argo_workflow_name": "dataset-ds-1",
        }
    )
    repo = FakeDatasetRepository(item)
    argo = CaptureArgoSubmitter()
    service = DatasetService(repo, FakeSettingsService(), argo_submitter=argo)

    response = service.retry_dataset("ds-1")

    assert response.status == "pending"
    assert response.detail_url == f"/datasets/{response.dataset_id}"
    assert repo.item.id == response.dataset_id
    submitted = argo.submitted
    assert submitted is not None
    workflow = submitted["json"]["workflow"]  # type: ignore[index]
    params = {param["name"]: param["value"] for param in workflow["spec"]["arguments"]["parameters"]}  # type: ignore[index]
    assert params["symbols"] == "AAPL"
    assert params["options-enabled"] == "false"
    assert repo.item.params_json["options"]["enabled"] is False
