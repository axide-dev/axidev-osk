[CmdletBinding()]
param(
    [string]$Python
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AccessibilityPath = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Accessibility"
$AccessibilityConfigurationName = "Configuration"
$NormalRegistrationName = "Axidev_AxidevOSK_Development_v1.0"
$ResourceDllName = "axidev-osk-resources.dll"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).ProviderPath
if (-not $Python) {
    $Python = Join-Path $RepoRoot ".venv-windows\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Windows Python was not found at $Python."
}

& $Python -c "import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    throw 'Install the Windows build dependency first: python -m pip install -e ".[windows-dev]"'
}

$SpecPath = Join-Path $PSScriptRoot "axidev-osk.spec"
$DistPath = Join-Path $RepoRoot "dist"
$WorkPath = Join-Path $RepoRoot "build\windows"
& $Python -m PyInstaller --noconfirm --clean --distpath $DistPath --workpath $WorkPath $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$BundlePath = Join-Path $DistPath "axidev-osk"
$ExecutablePath = Join-Path $BundlePath "axidev-osk.exe"
if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
    throw "PyInstaller did not create $ExecutablePath."
}
$BundledResourcePath = Join-Path $BundlePath $ResourceDllName
if (-not (Test-Path -LiteralPath $BundledResourcePath -PathType Leaf)) {
    $CollectedResourcePath = Join-Path $BundlePath "_internal\$ResourceDllName"
    if (-not (Test-Path -LiteralPath $CollectedResourcePath -PathType Leaf)) {
        throw "PyInstaller did not collect $ResourceDllName."
    }
    Move-Item -LiteralPath $CollectedResourcePath -Destination $BundledResourcePath
}

$CertificateSubject = "CN=Axidev OSK Development"
$Certificate = Get-ChildItem -Path "Cert:\CurrentUser\My" -CodeSigningCert |
    Where-Object {
        $_.Subject -eq $CertificateSubject -and
        $_.NotAfter -gt (Get-Date).AddDays(30)
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if ($null -eq $Certificate) {
    $Certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $CertificateSubject `
        -FriendlyName "Axidev OSK Development" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(2)
}

foreach ($signingTarget in @(
    [PSCustomObject]@{ Path = $ExecutablePath; Description = "executable" },
    [PSCustomObject]@{ Path = $BundledResourcePath; Description = "resource DLL" }
)) {
    $Signature = Set-AuthenticodeSignature `
        -LiteralPath $signingTarget.Path `
        -Certificate $Certificate `
        -HashAlgorithm SHA256 `
        -IncludeChain All
    if ($null -eq $Signature.SignerCertificate -or
        $Signature.SignerCertificate.Thumbprint -ne $Certificate.Thumbprint) {
        throw "PowerShell did not sign the $($signingTarget.Description) with the expected certificate."
    }
}

if (-not ([System.Management.Automation.PSTypeName]"AxidevTokenInfo").Type) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class AxidevTokenInfo
{
    private const uint TOKEN_QUERY = 0x0008;
    private const int TokenElevation = 20;
    private const int TokenUIAccess = 26;

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool GetTokenInformation(IntPtr tokenHandle, int tokenClass, out int value, int valueLength, out int returnLength);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    private static int ReadTokenValue(Process process, int tokenClass)
    {
        IntPtr token;
        if (!OpenProcessToken(process.Handle, TOKEN_QUERY, out token))
            throw new Win32Exception(Marshal.GetLastWin32Error());

        try
        {
            int value;
            int returnLength;
            if (!GetTokenInformation(token, tokenClass, out value, sizeof(int), out returnLength))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return value;
        }
        finally
        {
            CloseHandle(token);
        }
    }

    public static int UIAccess(Process process) { return ReadTokenValue(process, TokenUIAccess); }
    public static int Elevated(Process process) { return ReadTokenValue(process, TokenElevation); }
}
"@
}

function Start-DevelopmentAdmin {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$AdminScript`"",
        "-Mode", "Install",
        "-SourceDirectory", "`"$StagedBundle`"",
        "-CertificatePath", "`"$ExportedCertificate`"",
        "-CertificateThumbprint", $Certificate.Thumbprint,
        "-ShortcutPath", "`"$ShortcutPath`"",
        "-TransactionPath", "`"$TransactionPath`""
    )
    return Start-Process `
        -FilePath $PowerShell `
        -Verb RunAs `
        -PassThru `
        -ArgumentList $arguments
}

function Get-AccessibilityConfigurationState {
    if (-not (Test-Path -LiteralPath $AccessibilityPath)) {
        return [PSCustomObject]@{ Exists = $false; Value = "" }
    }
    $property = Get-ItemProperty -LiteralPath $AccessibilityPath -Name $AccessibilityConfigurationName -ErrorAction SilentlyContinue
    if ($null -eq $property) {
        return [PSCustomObject]@{ Exists = $false; Value = "" }
    }
    return [PSCustomObject]@{
        Exists = $true
        Value = [string]$property.$AccessibilityConfigurationName
    }
}

function Set-AccessibilityConfiguration([string]$Value) {
    New-Item -ItemType Directory -Path $AccessibilityPath -Force | Out-Null
    New-ItemProperty `
        -LiteralPath $AccessibilityPath `
        -Name $AccessibilityConfigurationName `
        -Value $Value `
        -PropertyType String `
        -Force | Out-Null
}

function Restore-AccessibilityConfiguration($State) {
    if ($State.Exists) {
        Set-AccessibilityConfiguration $State.Value
        return
    }
    Remove-ItemProperty `
        -LiteralPath $AccessibilityPath `
        -Name $AccessibilityConfigurationName `
        -Force `
        -ErrorAction SilentlyContinue
}

function Enable-AxidevAccessibilityAutoStart {
    $state = Get-AccessibilityConfigurationState
    $entries = @(
        $state.Value -split "," |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
    if ($entries -notcontains $NormalRegistrationName) {
        $entries += $NormalRegistrationName
    }
    Set-AccessibilityConfiguration ($entries -join ",")
}

function Disable-AxidevAccessibilityAutoStart {
    $state = Get-AccessibilityConfigurationState
    if (-not $state.Exists) {
        return
    }
    $entries = @(
        $state.Value -split "," |
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
    Set-AccessibilityConfiguration ($entries -join ",")
}

function Start-VerifiedApplication([string]$ExecutablePath) {
    $signature = Get-AuthenticodeSignature -LiteralPath $ExecutablePath
    if ($signature.Status -ne "Valid") {
        throw "The installed executable signature is not trusted: $($signature.Status)."
    }

    $process = Start-Process -FilePath $ExecutablePath -PassThru
    $startupDeadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $process.Refresh()
        if ($process.HasExited) {
            throw "The installed Axidev OSK process exited with code $($process.ExitCode)."
        }
    } while ($process.MainWindowHandle -eq 0 -and (Get-Date) -lt $startupDeadline)

    if ($process.MainWindowHandle -eq 0) {
        Stop-Process -Id $process.Id -Force
        throw "The installed Axidev OSK process did not create a window within 15 seconds."
    }

    Start-Sleep -Seconds 2
    $process.Refresh()
    if ($process.HasExited) {
        throw "The installed Axidev OSK process exited after creating its window."
    }

    $uiAccess = [AxidevTokenInfo]::UIAccess($process)
    $elevated = [AxidevTokenInfo]::Elevated($process)
    if ($uiAccess -ne 1) {
        Stop-Process -Id $process.Id -Force
        throw "The installed Axidev OSK process did not receive UIAccess."
    }

    return [PSCustomObject]@{
        Process = $process
        Signature = $signature
        UIAccess = $uiAccess
        Elevated = $elevated
    }
}

function Wait-ForAdminReady($Process) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        if (Test-Path -LiteralPath (Join-Path $TransactionPath "ready") -PathType Leaf) {
            return
        }
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "The elevated installation failed with exit code $($Process.ExitCode)."
        }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    throw "The elevated installation did not become ready within 30 seconds."
}

$NativeStage = Join-Path $env:LOCALAPPDATA "Axidev OSK Development\install-stage"
Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $NativeStage | Out-Null

try {
    $StagedBundle = Join-Path $NativeStage "bundle"
    New-Item -ItemType Directory -Path $StagedBundle | Out-Null
    Copy-Item -Path (Join-Path $BundlePath "*") -Destination $StagedBundle -Recurse -Force

    $TransactionPath = Join-Path $NativeStage "transaction"
    New-Item -ItemType Directory -Path $TransactionPath | Out-Null

    $ExportedCertificate = Join-Path $NativeStage "development-certificate.cer"
    Export-Certificate -Cert $Certificate -FilePath $ExportedCertificate -Force | Out-Null

    $AdminScript = Join-Path $NativeStage "development-admin.ps1"
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "development-admin.ps1") -Destination $AdminScript
    $PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $InstalledExecutable = Join-Path $env:ProgramFiles "Axidev OSK\axidev-osk.exe"
    $ShortcutPath = Join-Path ([Environment]::GetFolderPath("Programs")) "Axidev OSK.lnk"
    $PreviousAccessibilityConfiguration = Get-AccessibilityConfigurationState
    $AdminProcess = $null
    $InstallationCommitted = $false

    try {
        Disable-AxidevAccessibilityAutoStart
        $AdminProcess = Start-DevelopmentAdmin
        Wait-ForAdminReady $AdminProcess
        $Verification = Start-VerifiedApplication $InstalledExecutable
        Enable-AxidevAccessibilityAutoStart
        Set-Content -LiteralPath (Join-Path $TransactionPath "commit") -Value "commit" -NoNewline
        if (-not $AdminProcess.WaitForExit(30000)) {
            throw "The elevated installation did not commit within 30 seconds."
        }
        if ($AdminProcess.ExitCode -ne 0) {
            throw "The elevated installation failed with exit code $($AdminProcess.ExitCode)."
        }
        $InstallationCommitted = $true
    } catch {
        $installationFailure = $_
        Restore-AccessibilityConfiguration $PreviousAccessibilityConfiguration
        if ($null -ne $AdminProcess) {
            $AdminProcess.Refresh()
            if (-not $AdminProcess.HasExited) {
                Set-Content -LiteralPath (Join-Path $TransactionPath "rollback") `
                    -Value "rollback" -NoNewline
                if (-not $AdminProcess.WaitForExit(30000)) {
                    throw "Installation failed: $installationFailure`nThe elevated rollback timed out."
                }
            }
        }
        throw $installationFailure
    } finally {
        if (-not $InstallationCommitted -and $null -ne $AdminProcess) {
            $AdminProcess.Refresh()
            if (-not $AdminProcess.HasExited) {
                Set-Content -LiteralPath (Join-Path $TransactionPath "rollback") `
                    -Value "rollback" -NoNewline
                $AdminProcess.WaitForExit(30000) | Out-Null
            }
        }
    }
} finally {
    Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Installed: $InstalledExecutable"
Write-Host "Signature: $($Verification.Signature.Status)"
Write-Host "UIAccess: $($Verification.UIAccess)"
Write-Host "Elevated: $($Verification.Elevated)"
Write-Host "Process ID: $($Verification.Process.Id)"
