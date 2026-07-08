# File Management

## Commit To GitHub

- `webui/`: browser UI.
- `user_tools/`: local HTTP server, scenario runner, HydroDyn table editor logic, tests.
- `work_c4/config.py` and `work_c4/driver_c4.py`: FOCAL C4 path config and OpenFAST v4 compatibility helpers.
- `scenarios/`: editable example scenario JSON files.
- `scripts/`: PowerShell entry points for checking, launching the UI, generating cases, and running scenarios.
- `README.md`, `requirements.txt`, and lightweight setup notes.

## Keep Local Only

- `bin/openfast_x64.exe`: OpenFAST executable.
- `FOCAL_OpenFast_C4-main/FOCAL_OpenFast_C4-main/`: clean FOCAL C4 model template.
- `data/`: large experimental datasets.
- `runs/`: generated case folders and OpenFAST outputs.
- `reports/`: local figures and reports.

These local-only paths are ignored by `.gitignore`. Copy them into this folder for running on your machine, but do not stage them unless you intentionally switch to Git LFS or a separate data release.

## Generated Layout

Every scenario run copies the clean model template into:

```text
runs/<scenario>/<case>/
```

The runner edits only that copied case folder, then writes `scenario_summary.json` and the scenario-level `scenario_results.json`.
