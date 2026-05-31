from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.standalone.print_argo_payload import _decode_config_b64


def test_decode_config_b64_accepts_inline_b64() -> None:
    encoded = base64.b64encode(b"runs: []\n").decode("ascii")
    assert _decode_config_b64(encoded) == "runs: []\n"


def test_decode_config_b64_accepts_at_file(tmp_path: Path) -> None:
    encoded = base64.b64encode(b"runs: []\n").decode("ascii")
    arg_file = tmp_path / "argo_arg.txt"
    arg_file.write_text(encoded, encoding="utf-8")
    assert _decode_config_b64(f"@{arg_file}") == "runs: []\n"


def test_decode_config_b64_rejects_non_base64() -> None:
    with pytest.raises(ValueError):
        _decode_config_b64("not-base64")
