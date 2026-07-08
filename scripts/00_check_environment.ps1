param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"

Write-Host "== Python =="
python --version

Write-Host "`n== Python dependencies =="
@'
import importlib
for name in ["numpy", "scipy", "matplotlib"]:
    module = importlib.import_module(name)
    print(f"OK {name} {getattr(module, '__version__', '')}")
'@ | python -

Write-Host "`n== Path configuration =="
python .\work_c4\config.py

Write-Host "`n== Syntax check =="
python -m py_compile `
  .\user_tools\hydrodyn_tables.py `
  .\user_tools\run_scenario.py `
  .\user_tools\ui_server.py `
  .\work_c4\config.py `
  .\work_c4\driver_c4.py

Write-Host "`n== Unit tests =="
python -m unittest .\user_tools\test_hydrodyn_tables.py
