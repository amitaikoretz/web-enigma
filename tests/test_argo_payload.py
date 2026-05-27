from __future__ import annotations

from app.backtests.argo_payload import build_argo_launch_payload, format_argo_launch_curl


def test_build_argo_launch_payload_with_config_path() -> None:
    payload = build_argo_launch_payload(
        config_path="/data/backtest-results/job.yaml",
        split_by="symbol",
        backtest_id="abc123",
    )

    assert payload == {
        "config_path": "/data/backtest-results/job.yaml",
        "split_by": "symbol",
        "backtest_id": "abc123",
    }


def test_build_argo_launch_payload_with_config_text() -> None:
    payload = build_argo_launch_payload(
        config_text="runs:\n  - run_id: demo\n",
        split_by="symbol_strategy",
        backtest_id="job1",
    )

    assert payload == {
        "format": "yaml",
        "config_text": "runs:\n  - run_id: demo\n",
        "split_by": "symbol_strategy",
        "backtest_id": "job1",
    }


def test_build_argo_launch_payload_omits_empty_optional_fields() -> None:
    payload = build_argo_launch_payload(config_path="/data/config.yaml")

    assert payload == {"config_path": "/data/config.yaml"}


def test_build_argo_launch_payload_rejects_both_modes() -> None:
    try:
        build_argo_launch_payload(
            config_path="/data/config.yaml",
            config_text="runs: []",
        )
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_format_argo_launch_curl_escapes_multiline_yaml() -> None:
    payload = build_argo_launch_payload(
        config_text='runs:\n  - run_id: "quoted"\n',
        split_by="run",
    )
    curl = format_argo_launch_curl("http://localhost:8000", payload)

    assert curl.startswith("curl -sS -X POST 'http://localhost:8000/backtests/argo'")
    assert "-H 'Content-Type: application/json'" in curl
    assert '"config_text": "runs:\\n  - run_id: \\"quoted\\"\\n"' in curl
    assert '"split_by": "run"' in curl
