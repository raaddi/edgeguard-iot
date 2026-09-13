[CmdletBinding()]
param(
    [switch]$Offline,
    [switch]$Open
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$thesisDir = Join-Path $repoRoot 'thesis'
$buildDir = Join-Path $thesisDir 'build'
$localCompiler = Join-Path $repoRoot '.tools/tectonic.exe'
if ($env:TECTONIC) {
    $compiler = $env:TECTONIC
} elseif (Test-Path -LiteralPath $localCompiler) {
    $compiler = $localCompiler
} else {
    $command = Get-Command tectonic -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'Tectonic not found. Run scripts/setup-latex.ps1 while online.'
    }
    $compiler = $command.Source
}
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$compilerArgs = @('--untrusted', '--keep-logs', '--synctex', '--outdir', $buildDir)
if ($Offline) { $compilerArgs += '--only-cached' }
$compilerArgs += 'main.tex'
Push-Location $thesisDir
try {
    & $compiler @compilerArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'PDF build failed. Read thesis/build/main.log. Missing cached packages require one online build.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $buildDir 'main.pdf'))) {
        throw 'Compiler finished without producing main.pdf.'
    }
    Write-Host "PDF: $(Join-Path $buildDir 'main.pdf')"
    if ($Open) { Invoke-Item -LiteralPath (Join-Path $buildDir 'main.pdf') }
} finally {
    Pop-Location
}
