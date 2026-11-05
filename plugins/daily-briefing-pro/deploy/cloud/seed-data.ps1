[CmdletBinding()]
param(
    [string]$SourceDataDir = (Join-Path $HOME '.codex\daily-briefing-pro\data'),
    [string]$DestinationDataDir = '',
    [switch]$Apply,
    [switch]$RefreshExisting,
    [switch]$Force,
    [string]$Manifest = ''
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $DestinationDataDir) {
    $DestinationDataDir = Join-Path $scriptRoot 'runtime\data'
}

$python = Get-Command python -ErrorAction Stop
$seedScript = Join-Path $scriptRoot '..\..\skills\daily-briefing-pro\scripts\runtime_seed.py'
$seedScript = (Resolve-Path -LiteralPath $seedScript).Path

$arguments = @(
    '-X', 'utf8',
    $seedScript,
    '--source-dir', $SourceDataDir,
    '--destination-dir', $DestinationDataDir
)

if ($Apply) {
    $arguments += '--apply'
}
if ($RefreshExisting) {
    $arguments += '--refresh-existing'
}
if ($Force) {
    $arguments += '--force'
}
if ($Manifest) {
    $arguments += @('--manifest', $Manifest)
} elseif ($Apply) {
    $arguments += @('--manifest', (Join-Path $scriptRoot 'runtime\seed-data-manifest.json'))
}

& $python.Source @arguments
exit $LASTEXITCODE
