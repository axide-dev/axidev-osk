[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Commit", "Rollback", "Uninstall")]
    [string]$Mode,

    [string]$SourceDirectory,

    [string]$CertificatePath,

    [string]$CertificateThumbprint,

    [string]$ShortcutPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$InstallPath = Join-Path $env:ProgramFiles "Axidev OSK"
$NewPath = "$InstallPath.new"
$OldPath = "$InstallPath.old"
$MarkerName = "development-certificate-thumbprint.txt"
$PreviousMarkerName = "development-previous-certificate-thumbprint.txt"
$PendingMarkerName = "development-install-pending.txt"
$ShortcutMarkerName = "development-shortcut-pending.txt"

if (-not $ShortcutPath) {
    throw "The current user's Start Menu shortcut path is missing."
}
$ShortcutDirectory = Split-Path -Parent $ShortcutPath
$ShortcutBaseName = [IO.Path]::GetFileNameWithoutExtension($ShortcutPath)
$ShortcutNewPath = Join-Path $ShortcutDirectory "$ShortcutBaseName.new.lnk"
$ShortcutOldPath = Join-Path $ShortcutDirectory "$ShortcutBaseName.old.lnk"

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

function New-StartMenuShortcut([string]$Path) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $shell = New-Object -ComObject "WScript.Shell"
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = Join-Path $InstallPath "axidev-osk.exe"
    $shortcut.WorkingDirectory = $InstallPath
    $shortcut.Description = "Axidev OSK"
    $shortcut.Save()
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
    foreach ($path in @($ShortcutPath, $ShortcutNewPath, $ShortcutOldPath)) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
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
    Remove-Item -LiteralPath $ShortcutOldPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $InstallPath $ShortcutMarkerName) -Force -ErrorAction SilentlyContinue
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
        $shortcutMarker = Join-Path $InstallPath $ShortcutMarkerName
        if (Test-Path -LiteralPath $shortcutMarker -PathType Leaf) {
            $previousShortcut = (Get-Content -LiteralPath $shortcutMarker -Raw).Trim()
            if (Test-Path -LiteralPath $ShortcutOldPath -PathType Leaf) {
                Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue
                Move-Item -LiteralPath $ShortcutOldPath -Destination $ShortcutPath
            } elseif ($previousShortcut -eq "absent") {
                Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -LiteralPath $InstallPath -Recurse -Force -ErrorAction Stop
    }
    Remove-Item -LiteralPath $ShortcutNewPath -Force -ErrorAction SilentlyContinue
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
if (Test-Path -LiteralPath $ShortcutOldPath) {
    throw "A previous Start Menu shortcut transaction is still pending."
}
$previousThumbprint = Read-CertificateMarker $InstallPath $MarkerName
Remove-Item -LiteralPath $NewPath -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ShortcutNewPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $NewPath | Out-Null
Copy-Item -Path (Join-Path $SourceDirectory "*") -Destination $NewPath -Recurse -Force
Set-Content -LiteralPath (Join-Path $NewPath $MarkerName) -Value $CertificateThumbprint -NoNewline
Set-Content -LiteralPath (Join-Path $NewPath $PendingMarkerName) -Value "pending" -NoNewline
if ($previousThumbprint) {
    Set-Content -LiteralPath (Join-Path $NewPath $PreviousMarkerName) -Value $previousThumbprint -NoNewline
}
New-StartMenuShortcut $ShortcutNewPath

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

$shortcutState = if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) { "existing" } else { "absent" }
Set-Content -LiteralPath (Join-Path $InstallPath $ShortcutMarkerName) -Value $shortcutState -NoNewline
if ($shortcutState -eq "existing") {
    Move-Item -LiteralPath $ShortcutPath -Destination $ShortcutOldPath
}
Move-Item -LiteralPath $ShortcutNewPath -Destination $ShortcutPath
