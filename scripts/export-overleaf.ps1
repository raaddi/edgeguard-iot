# Create a standalone Overleaf project with main.tex at the archive root.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$thesisDir = Join-Path $repoRoot 'thesis'
$stage = Join-Path $repoRoot ('.tools/overleaf-' + [guid]::NewGuid().ToString('N'))
$outputDir = Join-Path $repoRoot 'output'
New-Item -ItemType Directory -Force -Path $stage,$outputDir | Out-Null
foreach ($file in Get-ChildItem -LiteralPath $thesisDir -Recurse -File) {
    $relative = $file.FullName.Substring($thesisDir.Length + 1)
    if ($relative -match '^(build[\\/]|config[\\/]private\.tex$)') { continue }
    if ($file.Extension -notin @('.tex','.bib','.md','.json','.png','.jpg','.jpeg','.pdf','.sty','.cls')) { continue }
    $destination = Join-Path $stage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'assets') | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot 'experiments/templates/run-manifest.example.json') -Destination (Join-Path $stage 'assets/run-manifest.example.json')
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'docs') | Out-Null
foreach ($guide in @('thesis-outline.md','workflow.md')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot "docs/$guide") -Destination (Join-Path $stage "docs/$guide")
}
$archive = Join-Path $outputDir 'EdgeGuard_Magisterka_Overleaf.zip'
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $archive -Force
Write-Host "Overleaf ZIP: $archive"
Write-Host "Choose main.tex and XeLaTeX after upload. Private author overrides are excluded."
