[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AccessibilityPath = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Accessibility"
$AccessibilityConfigurationName = "Configuration"
$NormalRegistrationName = "Axidev_AxidevOSK_Development_v1.0"

function Disable-AxidevAccessibilityAutoStart {
    if (-not (Test-Path -LiteralPath $AccessibilityPath)) {
        return
    }
    $property = Get-ItemProperty -LiteralPath $AccessibilityPath -Name $AccessibilityConfigurationName -ErrorAction SilentlyContinue
    if ($null -eq $property) {
        return
    }
    $entries = @(
        ([string]$property.$AccessibilityConfigurationName) -split "," |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -and $_ -ne $NormalRegistrationName }
    )
    if ($entries.Count -eq 0) {
        Remove-ItemProperty `
            -LiteralPath $AccessibilityPath `
            -Name $AccessibilityConfigurationName `
            -Force
        return
    }
    New-ItemProperty `
        -LiteralPath $AccessibilityPath `
        -Name $AccessibilityConfigurationName `
        -Value ($entries -join ",") `
        -PropertyType String `
        -Force | Out-Null
}

$NativeStage = Join-Path $env:LOCALAPPDATA "Axidev OSK Development\uninstall-stage"
Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $NativeStage | Out-Null

try {
    $AdminScript = Join-Path $NativeStage "development-admin.ps1"
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "development-admin.ps1") -Destination $AdminScript

    $PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $ShortcutPath = Join-Path ([Environment]::GetFolderPath("Programs")) "Axidev OSK.lnk"
    $AdminArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$AdminScript`"",
        "-Mode", "Uninstall",
        "-ShortcutPath", "`"$ShortcutPath`""
    )
    $AdminProcess = Start-Process -FilePath $PowerShell -Verb RunAs -Wait -PassThru -ArgumentList $AdminArguments
    if ($AdminProcess.ExitCode -ne 0) {
        throw "The elevated uninstall failed with exit code $($AdminProcess.ExitCode)."
    }
    Disable-AxidevAccessibilityAutoStart
} finally {
    Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Removed the Axidev OSK development install and its recorded certificate."
