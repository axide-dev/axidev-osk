# Trusted Windows Development Install

This directory builds a local Axidev OSK executable with Windows UIAccess.
It is a development workflow, not a distributable installer.

UIAccess lets the on-screen keyboard stay above other applications without
repeatedly rewriting window order. Windows grants it only to an executable
with an embedded UIAccess manifest, a trusted signature, and a protected
install location.

## Install Latest Release

Run the release bootstrap in Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm 'https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-windows-install.ps1' | iex"
```

The bootstrap downloads the latest source release, creates a private Python
environment under `%LOCALAPPDATA%`, and runs the trusted installer below.

## Source Build Requirements

- Windows 10 or newer
- Windows PowerShell 5.1
- The repository's `.venv-windows` environment
- The `axidev-io` submodule installed in that environment
- An account allowed to approve UAC prompts

Install the declared build dependency from the repository root:

```powershell
.\.venv-windows\Scripts\python.exe -m pip install -e ".[windows-dev]"
```

## Install From Source

Run the development installer from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install-development.ps1
```

The script performs these steps:

1. Builds a one-directory PyInstaller bundle under `dist\axidev-osk`.
2. Creates or reuses `CN=Axidev OSK Development` in the current user's certificate store.
3. Signs `axidev-osk.exe` with SHA-256.
4. Requests elevation to trust the certificate and stage the replacement.
5. Replaces `C:\Program Files\Axidev OSK`.
6. Launches the installed executable without elevation.
7. Keeps the previous install until startup and UIAccess checks pass.
8. Requests elevation to commit the verified replacement.
9. Reports its signature state, UIAccess token, elevation state, and process ID.

The expected final output includes:

```text
Signature: Valid
UIAccess: 1
```

The script creates no Start Menu entry and no startup entry. Those belong to
the future MSI installer.

## Uninstall

If you used the release bootstrap, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm 'https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-windows-install.ps1'))) -Uninstall"
```

For a source build, run the paired cleanup script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\uninstall-development.ps1
```

The script stops the installed process, removes `C:\Program Files\Axidev OSK`,
and removes only the certificate thumbprint recorded by the development
installer.

## Security Scope

The development certificate is local and self-signed. Do not export it with
its private key, commit it, or use it for public releases. The future MSI must
use a production Authenticode certificate and its own installer signing flow.
