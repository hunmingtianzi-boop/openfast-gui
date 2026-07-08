param(
    [string]$Scenario = ".\scenarios\steady_wind.json",
    [switch]$GenerateOnly,
    [switch]$ContinueOnFail,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"

$ArgsList = @(".\user_tools\run_scenario.py", "--scenario", $Scenario)
if ($GenerateOnly) { $ArgsList += "--generate-only" }
if ($ContinueOnFail) { $ArgsList += "--continue-on-fail" }
if ($Overwrite) { $ArgsList += "--overwrite" }

python @ArgsList
