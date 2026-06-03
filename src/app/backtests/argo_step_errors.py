from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Any, Callable, TypeVar

import typer

_DEFAULT_TMP_DIR = "/tmp"

_ERROR_EXCEPTION = "error-exception.txt"
_ERROR_CODE_LOCATION = "error-code-location.txt"
_ERROR_CALL_STACK = "error-call-stack.txt"
_ERROR_TRACEBACK = "error-traceback.txt"

T = TypeVar("T")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_error_outputs(tmp_dir: str = _DEFAULT_TMP_DIR) -> dict[str, Path]:
    """
    Pre-create/clear Argo error output files so the executor can always read them,
    even when a step fails early.
    """
    base = Path(tmp_dir)
    paths = {
        "error-exception": base / _ERROR_EXCEPTION,
        "error-code-location": base / _ERROR_CODE_LOCATION,
        "error-call-stack": base / _ERROR_CALL_STACK,
        "error-traceback": base / _ERROR_TRACEBACK,
    }

    for path in paths.values():
        _write_text(path, "")

    return paths


def write_exception_outputs(exc: BaseException, tmp_dir: str = _DEFAULT_TMP_DIR) -> None:
    paths = init_error_outputs(tmp_dir=tmp_dir)

    exc_type = type(exc).__name__
    message = str(exc).strip()
    one_liner = f"{exc_type}: {message}" if message else exc_type
    _write_text(paths["error-exception"], f"{one_liner}\n")

    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ is not None else []
    if frames:
        innermost = frames[-1]
        _write_text(paths["error-code-location"], f"{innermost.filename}:{innermost.lineno}\n")
        call_stack = "\n".join(f"{frame.filename}:{frame.lineno}" for frame in reversed(frames))
        _write_text(paths["error-call-stack"], f"{call_stack}\n" if call_stack else "")
    else:
        _write_text(paths["error-code-location"], "")
        _write_text(paths["error-call-stack"], "")

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _write_text(paths["error-traceback"], tb)


def _try_enable_faulthandler(tmp_dir: str) -> None:
    try:
        import faulthandler

        base = Path(tmp_dir)
        base.mkdir(parents=True, exist_ok=True)
        tb_path = base / _ERROR_TRACEBACK
        # Append so a fatal signal dump doesn't clobber an earlier Python traceback.
        f = tb_path.open("a", encoding="utf-8")
        faulthandler.enable(file=f, all_threads=True)
    except Exception:
        # Best-effort only; never block normal execution.
        return


def run_typer_app_with_argo_error_outputs(typer_app: Callable[[], Any], tmp_dir: str = _DEFAULT_TMP_DIR) -> None:
    """
    Run a Typer entrypoint while emitting standardized Argo error outputs for
    unexpected exceptions/crashes.

    Policy: exceptions only. Normal nonzero exits (including typer.Exit) should not
    populate error-* outputs.
    """
    init_error_outputs(tmp_dir=tmp_dir)
    _try_enable_faulthandler(tmp_dir=tmp_dir)

    try:
        typer_app()
    except typer.Exit:
        raise
    except SystemExit:
        # Treat "normal" SystemExit as a non-exceptional exit path for these outputs.
        raise
    except BaseException as exc:
        write_exception_outputs(exc, tmp_dir=tmp_dir)
        # Also emit details to logs (stderr) so Argo UI shows the error context immediately.
        exc_type = type(exc).__name__
        message = str(exc).strip()
        one_liner = f"{exc_type}: {message}" if message else exc_type
        try:
            typer.echo(one_liner, err=True)
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:
            # Never block error propagation due to logging issues.
            pass
        raise
