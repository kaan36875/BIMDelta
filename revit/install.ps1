<#
.SYNOPSIS
  Build the BIMDelta add-in and install it for the current Windows user.

.EXAMPLE
  .\install.ps1                    # every installed Revit from 2024 to 2027
  .\install.ps1 -RevitVersion 2027
  .\install.ps1 -Uninstall
#>
param(
    [ValidateSet("2024", "2025", "2026", "2027")]
    [string[]] $RevitVersion,
    [switch] $Uninstall
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$addins = Join-Path $env:APPDATA "Autodesk\Revit\Addins"

if (-not $RevitVersion) {
    $RevitVersion = "2024", "2025", "2026", "2027" | Where-Object {
        Test-Path (Join-Path $env:ProgramFiles "Autodesk\Revit $_\Revit.exe")
    }
    if (-not $RevitVersion) { throw "No Revit 2024-2027 found. Pass -RevitVersion." }
}

foreach ($v in $RevitVersion) {
    $target = Join-Path $addins $v
    $folder = Join-Path $target "BIMDelta"
    $manifest = Join-Path $target "BIMDelta.addin"

    if ($Uninstall) {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $folder, $manifest
        Write-Host "Removed BIMDelta from Revit $v"
        continue
    }

    Write-Host "Building for Revit $v..."
    dotnet build (Join-Path $here "BIMDelta.Revit\BIMDelta.Revit.csproj") -c Release -p:RevitVersion=$v --nologo -v quiet
    if ($LASTEXITCODE -ne 0) { throw "Build for Revit $v failed" }

    $output = Join-Path $here "BIMDelta.Revit\bin\Release\$v"
    New-Item -ItemType Directory -Force $folder | Out-Null
    Get-ChildItem $output -File | Where-Object Name -ne "BIMDelta.addin" |
        Copy-Item -Destination $folder -Force
    Copy-Item (Join-Path $output "BIMDelta.addin") $manifest -Force
    Write-Host "Installed for Revit $v in $target"
}

if (-not $Uninstall) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Warning "Git was not found. Install Git for Windows: https://git-scm.com/download/win"
    }
    if (-not (Get-Command bimdelta -ErrorAction SilentlyContinue)) {
        Write-Warning "bimdelta was not found. Install it with: pip install bimdelta"
    }
    Write-Host "Restart Revit to load the BIMDelta tab."
}
