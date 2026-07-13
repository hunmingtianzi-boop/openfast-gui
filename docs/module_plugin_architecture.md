# OpenFAST GUI module plugin architecture

## Completion boundary

The GUI treats a module as integrated when its files can be discovered,
classified, edited without changing the template, validated at the available
interface boundary, and written into a run directory. The selected model does
not need to contain every OpenFAST module. Missing modules remain visible in the
capability matrix as `not-in-model` and become active when a model references
their files.

The parser follows the two OpenFAST input conventions described in the
[official input-format overview](https://openfast.readthedocs.io/en/main/source/user/input_file_overview.html):
key/value files and legacy value-column files. It uses the labels printed in the
source model for visual grouping and preserves source lines during writeback.

## Layers

1. `module_plugins.py` registers module identity, stage, documentation,
   capabilities and important switch metadata.
2. `openfast_input.py` discovers dependencies and parses source sections,
   scalar fields, YAML fields, unit-header tables, 6x6 matrices and OutList
   blocks.
3. `ui_server.py` exposes the model catalog and one editable document at a time.
4. `app.js` renders source-order controls and stores edits in the current case.
5. `run_scenario.py` applies all edits only after copying the model to a case
   directory.

## Scenario fields

Line-addressed edits support duplicate keys, value-column files and ROSCO YAML:

```json
{
  "input_edits": [
    {
      "file": "IEA-15-240-RWT-UMaineSemi_ElastoDyn.dat",
      "line": 20,
      "kind": "value",
      "key": "PtfmSgDOF",
      "format": "openfast",
      "type": "boolean",
      "value": true
    }
  ]
}
```

Whole-file overrides support formats whose row count or layout must change.
`source_sha256` prevents a stale browser document from replacing a newer model
file:

```json
{
  "input_file_overrides": [
    {
      "file": "IEA-15-240-RWT/IEA-15-240-RWT_BeamDyn_blade.dat",
      "source_sha256": "...",
      "newline": "lf",
      "content": "..."
    }
  ]
}
```

Application order inside a generated case is:

1. full-file overrides;
2. line-addressed edits;
3. runtime compatibility normalization;
4. copied external assets and generated TurbSim input;
5. legacy `set` key overrides;
6. OutList, HydroDyn matrices and HydroDyn managed tables.

## Postprocessing and interfaces

`results_workspace.py` reads OpenFAST and FAST.Farm ASCII outputs and OpenFAST
binary outputs. `linearization_workspace.py` analyzes `.lin` state matrices.
`visualization_workspace.py` supplies bounded geometry payloads to the local
Three.js viewer.

Optional executables and libraries are configured through
`config/tool_profiles.json` plus the ignored local override. Process tools never
receive a shell command. Inputs are suffix-checked and staged under
`runs/external_tools/` before execution. Library and Simulink profiles are
availability contracts because they are loaded by an external host rather than
started as a standalone process.

