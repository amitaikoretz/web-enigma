# Agent Guidelines

- All Python scripts must use `typer`, not `argparse`.
- All Argo workflows must capture the invoked command line and forward it to an Argo output parameter (so it shows up in workflow outputs).
