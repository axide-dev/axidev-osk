# Trusted Windows Development Install

This directory builds a local Axidev OSK executable with Windows UIAccess.
It also registers Axidev OSK as a development accessibility application.
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
4. Requests one UAC confirmation for an elevated transaction helper.
5. Replaces `C:\Program Files\Axidev OSK` and its Start Menu shortcut.
6. Registers one Axidev accessibility application without launch arguments.
7. Keeps the elevated helper waiting while the normal process starts.
8. Verifies the installed process signature and UIAccess token.
9. Adds Axidev OSK to the current user's accessibility configuration.
10. Signals the helper to commit or rollback the replacement.
11. Reports its signature state, UIAccess token, elevation state, and process ID.

The expected final output includes:

```text
Signature: Valid
UIAccess: 1
```

Windows uses the same executable and normal runtime on every desktop. The
registration has no `StartParams` or alternate secure executable. Sign out
and back in after installation so Windows reloads the accessibility settings.

The development registration uses this stable identity:

```text
Axidev_AxidevOSK_Development_v1.0
```

The registration does not modify the Windows `osk` accessibility entry.
Microsoft's on-screen keyboard remains available as a fallback.

## Uninstall

If you used the release bootstrap, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm 'https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-windows-install.ps1'))) -Uninstall"
```

For a source build, run the paired cleanup script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\uninstall-development.ps1
```

The script stops the installed process, removes the Start Menu shortcut and
`C:\Program Files\Axidev OSK`, and removes only the certificate thumbprint
recorded by the development installer. It also removes only the Axidev
accessibility entry and its current-user configuration membership.

## Security Scope

The development certificate is local and self-signed. Do not export it with
its private key, commit it, or use it for public releases. Windows may run the
normal application under the `SYSTEM` account on secure desktops. The future
MSI must use a production Authenticode certificate, localizable registration
resources, and its own installer signing flow.
