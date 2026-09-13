# Install a pinned, portable Tectonic into this repository. No admin rights needed.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$toolsDir = Join-Path $repoRoot '.tools'
$archive = Join-Path $toolsDir 'tectonic-0.17.0-windows.zip'
$executable = Join-Path $toolsDir 'tectonic.exe'
$url = 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip'
$sha256 = 'f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f'
if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'This installer requires 64-bit Windows.'
}
if (Test-Path -LiteralPath $executable) {
    & $executable --version
    if ($LASTEXITCODE -ne 0) { throw 'Existing Tectonic could not start.' }
    Write-Host 'Tectonic is available. Run scripts/build-thesis.ps1 to prepare packages.'
    exit 0
}
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $sha256) { throw 'Tectonic download checksum mismatch. Installation stopped.' }
Expand-Archive -LiteralPath $archive -DestinationPath $toolsDir -Force
& $executable --version
if ($LASTEXITCODE -ne 0) { throw 'Tectonic could not start.' }
Write-Host 'Installed. Next: .\scripts\build-thesis.ps1 (first run needs Internet).'
