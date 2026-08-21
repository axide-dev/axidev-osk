[CmdletBinding()]
param(
    [string]$Python
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$Signature = Set-AuthenticodeSignature `
    -LiteralPath $ExecutablePath `
    -Certificate $Certificate `
    -HashAlgorithm SHA256 `
    -IncludeChain All
if ($null -eq $Signature.SignerCertificate -or
    $Signature.SignerCertificate.Thumbprint -ne $Certificate.Thumbprint) {
    throw "PowerShell did not sign the executable with the expected certificate."
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

function Invoke-DevelopmentAdmin([string]$Mode) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$AdminScript`"",
        "-Mode", $Mode,
        "-SourceDirectory", "`"$StagedBundle`"",
        "-CertificatePath", "`"$ExportedCertificate`"",
        "-CertificateThumbprint", $Certificate.Thumbprint
    )
    $process = Start-Process -FilePath $PowerShell -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    if ($process.ExitCode -ne 0) {
        throw "The elevated $Mode operation failed with exit code $($process.ExitCode)."
    }
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

$NativeStage = Join-Path $env:LOCALAPPDATA "Axidev OSK Development\install-stage"
Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $NativeStage | Out-Null

try {
    $StagedBundle = Join-Path $NativeStage "bundle"
    New-Item -ItemType Directory -Path $StagedBundle | Out-Null
    Copy-Item -Path (Join-Path $BundlePath "*") -Destination $StagedBundle -Recurse -Force

    $ExportedCertificate = Join-Path $NativeStage "development-certificate.cer"
    Export-Certificate -Cert $Certificate -FilePath $ExportedCertificate -Force | Out-Null

    $AdminScript = Join-Path $NativeStage "development-admin.ps1"
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "development-admin.ps1") -Destination $AdminScript
    $PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $InstalledExecutable = Join-Path $env:ProgramFiles "Axidev OSK\axidev-osk.exe"

    try {
        Invoke-DevelopmentAdmin "Install"
        $Verification = Start-VerifiedApplication $InstalledExecutable
        Invoke-DevelopmentAdmin "Commit"
    } catch {
        $installationFailure = $_
        try {
            Invoke-DevelopmentAdmin "Rollback"
        } catch {
            throw "Installation failed: $installationFailure`nRollback also failed: $_"
        }
        throw $installationFailure
    }
} finally {
    Remove-Item -LiteralPath $NativeStage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Installed: $InstalledExecutable"
Write-Host "Signature: $($Verification.Signature.Status)"
Write-Host "UIAccess: $($Verification.UIAccess)"
Write-Host "Elevated: $($Verification.Elevated)"
Write-Host "Process ID: $($Verification.Process.Id)"
