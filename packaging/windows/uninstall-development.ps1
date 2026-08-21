[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
} finally {
    Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Removed the Axidev OSK development install and its recorded certificate."
