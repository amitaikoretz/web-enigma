# Agent Guidelines


## General Script Guidelines
- All Python scripts must use `typer`, not `argparse`.


## Argo Workflows
- All Argo workflows should be backed by a YAML template and patched at launch time to plug in parameter values.
- Workflows should also be patched at launch time to insert retry clauses with backoff to catch cluster transient errors and OOM. For OOM, there should be a podspecpatch retry that increases memory on each attempt.
- All Argo workflows must capture the invoked command line and forward it to an Argo output parameter (so it shows up in workflow outputs).
- All Python-based Argo workflow steps must capture unhandled exceptions/crashes and emit these Argo output parameters (by writing them to files collected as output parameters):
  - `error-exception` — exception type/message (one line when possible)
  - `error-code-location` — innermost file:line where the failure originated
  - `error-call-stack` — ordered list of stack frames as `path:line` (one per line)
  - `error-traceback` — full traceback or other diagnostic body

## Platform
- All parquet files should have records backed by pydantic schemas.
- All first-class resources in the platform (backtests, models, etc) Should have a list view and page view (for an individual entity). There should be a delete button within the resource page view and a multiselet delete option in the list view.


## UI UX
- Pay careful attention to providing the user with a high-class stylish and functional UX UI experience.