[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Uninstall")]
    [string]$Mode,

    [string]$SourceDirectory,

    [string]$CertificatePath,

    [string]$CertificateThumbprint,

    [string]$ShortcutPath,

    [string]$TransactionPath
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
$RegistrationBackupName = "development-accessibility-registration.reg"
$RegistrationPresenceName = "development-accessibility-registration-presence.txt"
$RegistrationName = "Axidev_AxidevOSK_Development_v1.0"
$RegistrationPath = Join-Path `
    "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Accessibility\ATs" `
    $RegistrationName
$RegistrationNativePath = `
    "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Accessibility\ATs\$RegistrationName"

if (-not $ShortcutPath) {
    throw "The current user's Start Menu shortcut path is missing."
}
$ShortcutDirectory = Split-Path -Parent $ShortcutPath
$ShortcutBaseName = [IO.Path]::GetFileNameWithoutExtension($ShortcutPath)
$ShortcutNewPath = Join-Path $ShortcutDirectory "$ShortcutBaseName.new.lnk"
$ShortcutOldPath = Join-Path $ShortcutDirectory "$ShortcutBaseName.old.lnk"

function Stop-AxidevOsk {
    $deadline = (Get-Date).AddSeconds(10)
    $emptyChecks = 0
    do {
        $processes = @(Get-Process -Name "axidev-osk" -ErrorAction SilentlyContinue)
        if ($processes.Count -eq 0) {
            $emptyChecks += 1
            if ($emptyChecks -ge 4) {
                return
            }
        } else {
            $emptyChecks = 0
            $processes | Stop-Process -Force -ErrorAction Stop
            $processes | Wait-Process -Timeout 5 -ErrorAction Stop
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "Axidev OSK continued restarting during the elevated operation."
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

function Backup-AccessibilityRegistration([string]$Directory) {
    $presencePath = Join-Path $Directory $RegistrationPresenceName
    if (-not (Test-Path -LiteralPath $RegistrationPath)) {
        Set-Content -LiteralPath $presencePath -Value "absent" -NoNewline
        return
    }

    & reg.exe export `
        $RegistrationNativePath `
        (Join-Path $Directory $RegistrationBackupName) `
        /y | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to back up the Axidev accessibility registration."
    }
    Set-Content -LiteralPath $presencePath -Value "present" -NoNewline
}

function Restore-AccessibilityRegistration([string]$Directory) {
    Remove-Item -LiteralPath $RegistrationPath -Recurse -Force -ErrorAction SilentlyContinue
    $presencePath = Join-Path $Directory $RegistrationPresenceName
    if (-not (Test-Path -LiteralPath $presencePath -PathType Leaf)) {
        return
    }
    if ((Get-Content -LiteralPath $presencePath -Raw).Trim() -ne "present") {
        return
    }

    & reg.exe import (Join-Path $Directory $RegistrationBackupName) | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to restore the Axidev accessibility registration."
    }
}

function Remove-RegistrationBackup([string]$Directory) {
    Remove-Item `
        -LiteralPath (Join-Path $Directory $RegistrationBackupName) `
        -Force `
        -ErrorAction SilentlyContinue
    Remove-Item `
        -LiteralPath (Join-Path $Directory $RegistrationPresenceName) `
        -Force `
        -ErrorAction SilentlyContinue
}

function Install-AccessibilityRegistration {
    $profile = '<HCIModel><Accommodation type="severe dexterity"/></HCIModel>'
    New-Item -ItemType Directory -Path $RegistrationPath -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "ApplicationName" `
        -Value "Axidev OSK Development" -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "Description" `
        -Value "Axidev OSK development on-screen keyboard." -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "ATExe" `
        -Value "axidev-osk.exe" -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "Profile" `
        -Value $profile -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "SimpleProfile" `
        -Value "On-screen keyboard" -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "StartExe" `
        -Value (Join-Path $InstallPath "axidev-osk.exe") -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $RegistrationPath -Name "TerminateOnDesktopSwitch" `
        -Value 1 -PropertyType DWord -Force | Out-Null
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

function Commit-Installation {
    $currentThumbprint = Read-CertificateMarker $InstallPath $MarkerName
    $previousThumbprint = Read-CertificateMarker $InstallPath $PreviousMarkerName
    Remove-Item -LiteralPath $OldPath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ShortcutOldPath -Force -ErrorAction SilentlyContinue
    Remove-Item `
        -LiteralPath (Join-Path $InstallPath $ShortcutMarkerName) `
        -Force `
        -ErrorAction SilentlyContinue
    Remove-Item `
        -LiteralPath (Join-Path $InstallPath $PreviousMarkerName) `
        -Force `
        -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $InstallPath $PendingMarkerName) -Force
    Remove-RegistrationBackup $InstallPath
    if ($previousThumbprint -and $previousThumbprint -ne $currentThumbprint) {
        Remove-DevelopmentCertificate $previousThumbprint
    }
}

function Rollback-Installation {
    $installIsPending = Test-Path `
        -LiteralPath (Join-Path $InstallPath $PendingMarkerName) `
        -PathType Leaf
    $backupDirectory = if ($installIsPending) { $InstallPath } else { $NewPath }
    if (Test-Path -LiteralPath $backupDirectory -PathType Container) {
        Restore-AccessibilityRegistration $backupDirectory
    }

    $failedThumbprint = if ($installIsPending) {
        Read-CertificateMarker $InstallPath $MarkerName
    } else {
        $CertificateThumbprint
    }
    $previousThumbprint = if ($installIsPending) {
        Read-CertificateMarker $InstallPath $PreviousMarkerName
    } else {
        Read-CertificateMarker $InstallPath $MarkerName
    }

    Stop-AxidevOsk
    if ($installIsPending) {
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
    Remove-Item -LiteralPath $RegistrationPath -Recurse -Force -ErrorAction SilentlyContinue
    $thumbprints | Where-Object { $_ } | Select-Object -Unique | ForEach-Object {
        Remove-DevelopmentCertificate $_
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
if (-not $TransactionPath -or -not (Test-Path -LiteralPath $TransactionPath -PathType Container)) {
    throw "The installation transaction directory is missing."
}

$sourceExecutable = Join-Path $SourceDirectory "axidev-osk.exe"
$sourceSignature = Get-AuthenticodeSignature -LiteralPath $sourceExecutable
if ($null -eq $sourceSignature.SignerCertificate -or
    $sourceSignature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
    throw "The staged executable was not signed by the expected development certificate."
}

try {
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
    Set-Content -LiteralPath (Join-Path $NewPath $MarkerName) `
        -Value $CertificateThumbprint -NoNewline
    Set-Content -LiteralPath (Join-Path $NewPath $PendingMarkerName) `
        -Value "pending" -NoNewline
    if ($previousThumbprint) {
        Set-Content -LiteralPath (Join-Path $NewPath $PreviousMarkerName) `
            -Value $previousThumbprint -NoNewline
    }
    New-StartMenuShortcut $ShortcutNewPath

    $installedSignature = Get-AuthenticodeSignature `
        -LiteralPath (Join-Path $NewPath "axidev-osk.exe")
    if ($installedSignature.Status -ne "Valid") {
        throw "The staged executable signature is not trusted: $($installedSignature.Status)."
    }

    Backup-AccessibilityRegistration $NewPath
    Stop-AxidevOsk
    if (Test-Path -LiteralPath $InstallPath) {
        Move-Item -LiteralPath $InstallPath -Destination $OldPath
    }
    Move-Item -LiteralPath $NewPath -Destination $InstallPath

    $shortcutState = if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
        "existing"
    } else {
        "absent"
    }
    Set-Content -LiteralPath (Join-Path $InstallPath $ShortcutMarkerName) `
        -Value $shortcutState -NoNewline
    if ($shortcutState -eq "existing") {
        Move-Item -LiteralPath $ShortcutPath -Destination $ShortcutOldPath
    }
    Move-Item -LiteralPath $ShortcutNewPath -Destination $ShortcutPath
    Install-AccessibilityRegistration

    Set-Content -LiteralPath (Join-Path $TransactionPath "ready") `
        -Value "ready" -NoNewline
    $deadline = (Get-Date).AddSeconds(90)
    do {
        if (Test-Path -LiteralPath (Join-Path $TransactionPath "commit") -PathType Leaf) {
            Commit-Installation
            return
        }
        if (Test-Path -LiteralPath (Join-Path $TransactionPath "rollback") -PathType Leaf) {
            throw "The parent installer requested rollback."
        }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    throw "The parent installer did not finish the transaction within 90 seconds."
} catch {
    $installationFailure = $_
    try {
        Rollback-Installation
    } catch {
        throw "Installation failed: $installationFailure`nRollback also failed: $_"
    }
    throw $installationFailure
}
