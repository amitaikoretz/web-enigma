# Agent Guidelines


## General Script Guidelines
- All Python scripts must use `typer`, not `argparse`.


## Argo Workflows
- All Argo workflows should be backed by a YAML template and patched at launch time to plug in parameter values.
- Parallel steps should track progress (0/100) and aggregate it at the step level.
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


## Frontend Work Must Meet Product-Quality Standards

Frontend changes should not stop at “it works.” Every UI contribution should aim for a polished, coherent, production-ready user experience.

For any user-facing change:

- Make the interface clear, attractive, and intentionally designed.

- Match the existing visual language of the app.

- Pay attention to spacing, alignment, typography, hierarchy, and interaction states.

- Include appropriate loading, empty, error, and success states.

- Ensure the UI works well on both desktop and mobile layouts.

- Preserve accessibility: semantic structure, keyboard navigation, visible focus states, readable contrast, and clear labels.

- Use concise, human-friendly copy.

- Avoid raw, unstyled, or generic-looking controls when a more considered presentation is appropriate.

- Prefer reusable components and established project patterns.

- Do not introduce new styling frameworks or component libraries without strong justification.
A task that changes the frontend is incomplete if the result is confusing, visually inconsistent, inaccessible, or obviously unfinished, even if the underlying functionality works.