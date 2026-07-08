param(
    [string]$Scenario = ".\scenarios\steady_wind.json",
    [string]$Model = "",
    [string]$OpenFastExe = "",
    [ValidateSet("v4", "v5")]
    [string]$RuntimeFormat = "v4",
    [ValidateSet("focal_c4_v4", "none")]
    [string]$Compatibility = "focal_c4_v4",
    [string]$Fst = "",
    [switch]$GenerateOnly,
    [switch]$ContinueOnFail,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"

$ArgsList = @(".\user_tools\run_scenario.py", "--scenario", $Scenario)
if ($Model) { $ArgsList += @("--model", $Model) }
if ($OpenFastExe) { $ArgsList += @("--openfast-exe", $OpenFastExe) }
if ($RuntimeFormat) { $ArgsList += @("--runtime-format", $RuntimeFormat) }
if ($Compatibility) { $ArgsList += @("--compatibility", $Compatibility) }
if ($Fst) { $ArgsList += @("--fst", $Fst) }
if ($GenerateOnly) { $ArgsList += "--generate-only" }
if ($ContinueOnFail) { $ArgsList += "--continue-on-fail" }
if ($Overwrite) { $ArgsList += "--overwrite" }

python @ArgsList
