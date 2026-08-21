[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Commit", "Rollback", "Uninstall")]
    [string]$Mode,

    [string]$SourceDirectory,

    [string]$CertificatePath,

    [string]$CertificateThumbprint
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$InstallPath = Join-Path $env:ProgramFiles "Axidev OSK"
$NewPath = "$InstallPath.new"
$OldPath = "$InstallPath.old"
$MarkerName = "development-certificate-thumbprint.txt"
$PreviousMarkerName = "development-previous-certificate-thumbprint.txt"
$PendingMarkerName = "development-install-pending.txt"

function Stop-AxidevOsk {
    $processes = @(Get-Process -Name "axidev-osk" -ErrorAction SilentlyContinue)
    $processes | Stop-Process -Force -ErrorAction Stop
    $processes | Wait-Process -Timeout 10 -ErrorAction Stop
}

function Remove-DevelopmentCertificate([string]$Thumbprint) {
    if (-not $Thumbprint) {
        return
    }

    foreach ($store in @(
        "Cert:\LocalMachine\Root",
        "Cert:\LocalMachine\TrustedPublisher",
        "Cert:\CurrentUser\My"
    )) {
        Get-ChildItem -Path $store |
            Where-Object Thumbprint -eq $Thumbprint |
            Remove-Item -Force
    }
}

function Read-CertificateMarker([string]$Directory, [string]$Name) {
    $marker = Join-Path $Directory $Name
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        return ""
    }
    return (Get-Content -LiteralPath $marker -Raw).Trim()
}

if ($Mode -eq "Uninstall") {
    Stop-AxidevOsk
    $thumbprints = @()
    foreach ($path in @($InstallPath, $NewPath, $OldPath)) {
        $thumbprints += Read-CertificateMarker $path $MarkerName
        $thumbprints += Read-CertificateMarker $path $PreviousMarkerName
    }

    foreach ($path in @($InstallPath, $NewPath, $OldPath)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
        }
    }
    $thumbprints | Where-Object { $_ } | Select-Object -Unique | ForEach-Object {
        Remove-DevelopmentCertificate $_
    }
    return
}

if ($Mode -eq "Commit") {
    $pendingMarker = Join-Path $InstallPath $PendingMarkerName
    if (-not (Test-Path -LiteralPath $pendingMarker -PathType Leaf)) {
        throw "No verified development install is pending commit."
    }
    $currentThumbprint = Read-CertificateMarker $InstallPath $MarkerName
    $previousThumbprint = Read-CertificateMarker $InstallPath $PreviousMarkerName
    Remove-Item -LiteralPath $OldPath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $InstallPath $PreviousMarkerName) -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pendingMarker -Force
    if ($previousThumbprint -and $previousThumbprint -ne $currentThumbprint) {
        Remove-DevelopmentCertificate $previousThumbprint
    }
    return
}

if ($Mode -eq "Rollback") {
    $installIsPending = Test-Path -LiteralPath (Join-Path $InstallPath $PendingMarkerName) -PathType Leaf
    if ($installIsPending) {
        $failedThumbprint = Read-CertificateMarker $InstallPath $MarkerName
        $previousThumbprint = Read-CertificateMarker $InstallPath $PreviousMarkerName
    } else {
        $failedThumbprint = $CertificateThumbprint
        $previousThumbprint = Read-CertificateMarker $InstallPath $MarkerName
    }

    if ($installIsPending) {
        Stop-AxidevOsk
        Remove-Item -LiteralPath $InstallPath -Recurse -Force -ErrorAction Stop
    }
    Remove-Item -LiteralPath $NewPath -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $OldPath) {
        Move-Item -LiteralPath $OldPath -Destination $InstallPath
    }
    if ($failedThumbprint -and $failedThumbprint -ne $previousThumbprint) {
        Remove-DevelopmentCertificate $failedThumbprint
    }
    return
}

if (-not $SourceDirectory -or -not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
    throw "The staged Axidev OSK bundle is missing."
}
if (-not $CertificatePath -or -not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
    throw "The exported development certificate is missing."
}
if (-not $CertificateThumbprint) {
    throw "The development certificate thumbprint is missing."
}

$sourceExecutable = Join-Path $SourceDirectory "axidev-osk.exe"
$sourceSignature = Get-AuthenticodeSignature -LiteralPath $sourceExecutable
if ($null -eq $sourceSignature.SignerCertificate -or
    $sourceSignature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
    throw "The staged executable was not signed by the expected development certificate."
}

Import-Certificate -FilePath $CertificatePath -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null
Import-Certificate -FilePath $CertificatePath -CertStoreLocation "Cert:\LocalMachine\TrustedPublisher" | Out-Null

if (Test-Path -LiteralPath $OldPath) {
    throw "A previous development install transaction is still pending."
}
$previousThumbprint = Read-CertificateMarker $InstallPath $MarkerName
Remove-Item -LiteralPath $NewPath -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $NewPath | Out-Null
Copy-Item -Path (Join-Path $SourceDirectory "*") -Destination $NewPath -Recurse -Force
Set-Content -LiteralPath (Join-Path $NewPath $MarkerName) -Value $CertificateThumbprint -NoNewline
Set-Content -LiteralPath (Join-Path $NewPath $PendingMarkerName) -Value "pending" -NoNewline
if ($previousThumbprint) {
    Set-Content -LiteralPath (Join-Path $NewPath $PreviousMarkerName) -Value $previousThumbprint -NoNewline
}

$installedSignature = Get-AuthenticodeSignature -LiteralPath (Join-Path $NewPath "axidev-osk.exe")
if ($installedSignature.Status -ne "Valid") {
    Remove-Item -LiteralPath $NewPath -Recurse -Force
    throw "The staged executable signature is not trusted: $($installedSignature.Status)."
}

Stop-AxidevOsk
if (Test-Path -LiteralPath $InstallPath) {
    Move-Item -LiteralPath $InstallPath -Destination $OldPath
}

try {
    Move-Item -LiteralPath $NewPath -Destination $InstallPath
} catch {
    if (Test-Path -LiteralPath $OldPath) {
        Move-Item -LiteralPath $OldPath -Destination $InstallPath
    }
    throw
}
