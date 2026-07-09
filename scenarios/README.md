# Scenario Files

Use these JSON files for non-free-decay OpenFAST runs. Each scenario contains a list of cases. Every case copies the clean FOCAL C4 model into `runs/<scenario>/<case>/`, edits input files there, and runs OpenFAST inside the copied folder.

Scenarios may also include `model_id` and `runtime_id`. The GUI uses those fields to select the configured model/runtime profile before loading template keys or running cases. `iea_15_240_steady_wind.json` is the starter profile for the local IEA-15-240-RWT UMaineSemi model.
`iea_15_240_irregular_wave.json` adds IEA-15-240 irregular-wave cases for the local OpenFAST 2026/v5 runtime.

`focal_irregular_wave_compare.json` contains FOCAL C4 irregular-wave cases for the local experiment data in
`D:\OpenFast\FOCAL_C4_workflow_hub\00_shared_assets\raw_data\focal_c4_organized\04_irregular_wave`.
The GUI shows `webui/assets/irregular_wave/experiment_overview.png` as a reference figure for comparing simulation results.
If `运行后出图` is checked before running, the runner writes the per-case comparison PNG/PDF configured by
`case.comparison.mode` under `runs/<scenario>/<case>/comparison/` and publishes the PNG to the GUI run-log tab.
FOCAL cases use experiment-vs-simulation plots; IEA 15MW paper-reproduction cases use report metric checks.
Regenerate the figure with:

```powershell
python .\user_tools\plot_irregular_wave_experiment.py
```

Run a scenario:

```powershell
.\scripts\06_run_scenario_file.ps1 -Scenario .\scenarios\steady_wind.json
```

Generate input folders without running OpenFAST:

```powershell
.\scripts\06_run_scenario_file.ps1 -Scenario .\scenarios\wind_wave_regular.json -GenerateOnly
```

Edit syntax:

```json
"set": {
  "FOCAL_C4.fst": {
    "TMax": 300,
    "CompInflow": 1
  },
  "FOCAL_C4_InflowFile.dat": {
    "WindType": 1,
    "HWindSpeed": 12.8
  }
}
```

Matrix edits use 1-based indices:

```json
"matrix_edits": [
  {"block": "BQuad", "i": 4, "j": 4, "value": 60000000000.0}
]
```
