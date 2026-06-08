from __future__ import annotations

from app.daily_index_forecast.argo_workflow import build_daily_index_forecast_workflow_spec


def _template(spec: dict, name: str) -> dict:
    for tmpl in spec.get("templates", []):
        if tmpl.get("name") == name:
            return tmpl
    raise AssertionError(f"template {name!r} not found")


def test_daily_index_forecast_workflow_passes_group_id_to_all_steps() -> None:
    spec = build_daily_index_forecast_workflow_spec(
        group_id="group-123",
        feature_run_id="feature-run-123",
        universe_json="{}",
        feature_config_json="{}",
        walk_forward_json="{}",
        train_config_json="{}",
        costs_json="{}",
        data_cache_json="{}",
        artifact_dir="/tmp/daily-index-forecast/group",
        feature_artifact_dir="/tmp/daily-index-forecast/feature-run",
        family="daily_index_forecast",
    )

    main = _template(spec, "daily-index-forecast")
    volume_names = {item["name"] for item in spec.get("volumes", [])}
    assert "workspace" in volume_names
    assert "backtest-results" in volume_names

    step_names = [step["name"] for group in main["steps"] for step in group]
    assert step_names[0] == "print-payload"

    for step_group in main["steps"][1:]:
        step = step_group[0]
        params = {item["name"]: item["value"] for item in step["arguments"]["parameters"]}
        assert params["group-id"] == "{{workflow.parameters.group-id}}"

    print_payload = _template(spec, "print-payload")
    args = print_payload["container"]["args"]
    assert "--command-line" in args
    assert "__COMMAND_LINE__" not in args

    extract = _template(spec, "extract-features")
    extract_inputs = {item["name"] for item in extract["inputs"]["parameters"]}
    assert "group-id" in extract_inputs


def test_daily_index_forecast_train_step_sets_argo_progress_file() -> None:
    spec = build_daily_index_forecast_workflow_spec(
        group_id="group-123",
        feature_run_id="feature-run-123",
        universe_json="{}",
        feature_config_json="{}",
        walk_forward_json="{}",
        train_config_json="{}",
        costs_json="{}",
        data_cache_json="{}",
        artifact_dir="/tmp/daily-index-forecast/group",
        feature_artifact_dir="/tmp/daily-index-forecast/feature-run",
        family="daily_index_forecast",
    )

    train = _template(spec, "train-evaluate")
    env = {item["name"]: item["value"] for item in train["container"].get("env", [])}
    assert env["ARGO_PROGRESS_FILE"] == "/tmp/argo-progress.txt"


def test_daily_index_forecast_all_steps_set_argo_progress_file() -> None:
    spec = build_daily_index_forecast_workflow_spec(
        group_id="group-123",
        feature_run_id="feature-run-123",
        universe_json="{}",
        feature_config_json="{}",
        walk_forward_json="{}",
        train_config_json="{}",
        costs_json="{}",
        data_cache_json="{}",
        artifact_dir="/tmp/daily-index-forecast/group",
        feature_artifact_dir="/tmp/daily-index-forecast/feature-run",
        family="daily_index_forecast",
    )

    for template_name in ["extract-features", "generate-labels", "train-evaluate", "register-results"]:
        template = _template(spec, template_name)
        env = {item["name"]: item["value"] for item in template["container"].get("env", [])}
        assert env["ARGO_PROGRESS_FILE"] == "/tmp/argo-progress.txt"
