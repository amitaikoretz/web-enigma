# Agent Guidelines

- All Python scripts must use `typer`, not `argparse`.
- All Argo workflows must capture the invoked command line and forward it to an Argo output parameter (so it shows up in workflow outputs).
- All Python-based Argo workflow steps must capture unhandled exceptions/crashes and emit these Argo output parameters (by writing them to files collected as output parameters):
  - `error-exception` — exception type/message (one line when possible)
  - `error-code-location` — innermost file:line where the failure originated
  - `error-call-stack` — ordered list of stack frames as `path:line` (one per line)
  - `error-traceback` — full traceback or other diagnostic body
