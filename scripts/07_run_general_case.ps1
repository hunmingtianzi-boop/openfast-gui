param(
    [string]$Name = "manual_general",
    [double]$TMax = 120,
    [Nullable[double]]$WindSpeed = $null,
    [Nullable[int]]$WaveMod = $null,
    [Nullable[double]]$WaveHs = $null,
    [Nullable[double]]$WaveTp = $null,
    [string[]]$Set = @(),
    [string[]]$MatrixEdit = @(),
    [switch]$GenerateOnly,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"

$ArgsList = @(
  ".\user_tools\run_scenario.py",
  "--scenario-name", "manual_general",
  "--name", $Name,
  "--tmax", "$TMax"
)

if ($null -ne $WindSpeed) { $ArgsList += @("--wind-speed", "$WindSpeed") }
if ($null -ne $WaveMod) { $ArgsList += @("--wave-mod", "$WaveMod") }
if ($null -ne $WaveHs) { $ArgsList += @("--wave-hs", "$WaveHs") }
if ($null -ne $WaveTp) { $ArgsList += @("--wave-tp", "$WaveTp") }
foreach ($item in $Set) { $ArgsList += @("--set", $item) }
foreach ($item in $MatrixEdit) { $ArgsList += @("--matrix-edit", $item) }
if ($GenerateOnly) { $ArgsList += "--generate-only" }
if ($Overwrite) { $ArgsList += "--overwrite" }

python @ArgsList
