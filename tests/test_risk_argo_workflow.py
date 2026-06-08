from __future__ import annotations

from app.risk.argo_workflow import build_risk_model_workflow_spec


def _extract_template(spec: dict, name: str) -> dict:
    for tmpl in spec.get("templates", []):
        if tmpl.get("name") == name:
            return tmpl
    raise AssertionError(f"template {name!r} not found")


def test_risk_workflow_templates_have_terminal_and_error_outputs() -> None:
    spec = build_risk_model_workflow_spec(
        group_id="g1",
        family="risk",
        backtest_ids_json='["b1"]',
        dataset_config_json="{}",
        train_config_json="{}",
        artifact_dir="/data/backtest-results/risk-models/g1",
    )

    main = _extract_template(spec, "main")
    step_names = [step["name"] for group in main["steps"] for step in group]
    assert step_names == ["print-payload", "build-dataset", "train-stop", "train-mae", "register-results"]

    print_payload = _extract_template(spec, "print-payload")
    args = print_payload["container"]["args"]
    assert "--command-line" in args
    assert "__COMMAND_LINE__" not in args

    for name in ["build-dataset", "train-stop", "train-mae", "register-results"]:
        tmpl = _extract_template(spec, name)
        outputs = tmpl.get("outputs", {})
        params = outputs.get("parameters", [])
        names = {p.get("name") for p in params}
        assert "terminal-command" in names
        assert "error-exception" in names
        assert "error-code-location" in names
        assert "error-call-stack" in names
        assert "error-traceback" in names

    register = _extract_template(spec, "register-results")
    args = register["container"]["args"]
    assert "--family" in args
