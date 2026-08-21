[CmdletBinding()]
param(
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ReleaseBaseUrl = "https://github.com/axide-dev/axidev-osk/releases/latest/download"
$SourceArchiveUrl = "$ReleaseBaseUrl/axidev-osk-source.zip"
$CacheRoot = Join-Path $env:LOCALAPPDATA "Axidev OSK Development\release-install"
$SourceRoot = Join-Path $CacheRoot "source"
$InstallerPath = Join-Path $SourceRoot "packaging\windows\install-development.ps1"
$UninstallerPath = Join-Path $SourceRoot "packaging\windows\uninstall-development.ps1"

[Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Update-ReleaseSource {
    $stageRoot = Join-Path $CacheRoot "source-stage"
    $archivePath = Join-Path $stageRoot "axidev-osk-source.zip"
    $expandedRoot = Join-Path $stageRoot "expanded"

    Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $expandedRoot -Force | Out-Null

    try {
        Write-Host "Downloading the latest Axidev OSK release..."
        Invoke-WebRequest -UseBasicParsing -Uri $SourceArchiveUrl -OutFile $archivePath
        Expand-Archive -LiteralPath $archivePath -DestinationPath $expandedRoot -Force

        $stagedSource = Join-Path $expandedRoot "axidev-osk"
        $stagedInstaller = Join-Path $stagedSource "packaging\windows\install-development.ps1"
        $stagedUninstaller = Join-Path $stagedSource "packaging\windows\uninstall-development.ps1"
        $stagedBackend = Join-Path $stagedSource "vendor\axidev-io-python\pyproject.toml"
        if (-not (Test-Path -LiteralPath $stagedInstaller -PathType Leaf) -or
            -not (Test-Path -LiteralPath $stagedUninstaller -PathType Leaf) -or
            -not (Test-Path -LiteralPath $stagedBackend -PathType Leaf)) {
            throw "The latest release does not contain the trusted Windows installer and vendored input backend."
        }

        Remove-Item -LiteralPath $SourceRoot -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $stagedSource -Destination $SourceRoot
    } finally {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($Uninstall) {
    try {
        Update-ReleaseSource
    } catch {
        if (-not (Test-Path -LiteralPath $UninstallerPath -PathType Leaf)) {
            throw
        }
        Write-Warning "The latest release could not be downloaded. Using the cached uninstaller: $_"
    }

    & $UninstallerPath
    Remove-Item -LiteralPath $CacheRoot -Recurse -Force -ErrorAction SilentlyContinue
    return
}

Update-ReleaseSource

$pythonCommand = Get-Command "py.exe" -ErrorAction SilentlyContinue
$pythonArguments = @("-3")
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
    $pythonArguments = @()
}
if ($null -eq $pythonCommand) {
    throw "Python 3.10 or newer was not found. Install Python from https://www.python.org/downloads/windows/."
}

& $pythonCommand.Source @pythonArguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required."
}

$venvRoot = Join-Path $SourceRoot ".venv-windows"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $pythonCommand.Source @pythonArguments -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not create the Windows environment."
    }
}

$backendPath = Join-Path $SourceRoot "vendor\axidev-io-python"
& $venvPython -m pip install -e $backendPath -e "$SourceRoot[windows-dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Python package installation failed with exit code $LASTEXITCODE."
}

& $InstallerPath -Python $venvPython
