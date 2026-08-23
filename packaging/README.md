Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode.
Every call here is inayayousfi's, and no agent acted on its own.

# Packaging

This directory contains Axidev OSK installers, native package recipes, build support, and platform resources.

## Layout

```text
packaging/
  README.md
  MANUAL_INSTALL.md
  arch/
  deb/
  linux/
    README.md
    build_support/
    container/
    launcher/
    resources/
    install.sh
    install-from-source.sh
    release-lock.json
    uninstall.sh
  windows/
  nix/
  rpm/
```

The `packaging/build.py` command routes Linux payload, verification, release, and virtual-machine work.

## Linux Distribution

The release payload owns the Axidev OSK Python package, native input extension, static launcher, desktop entry, icon, metadata, and license files. The host supplies `/usr/bin/python3`, PySide6, Qt, Qt Wayland, LayerShellQt, and normal desktop libraries.

A normal installation uses these paths:

```text
/opt/axidev-osk/                  active payload
/opt/axidev-osk.old/              retained rollback payload
/usr/local/bin/axidev-osk         launcher symlink
/usr/local/sbin/axidev-osk-install
/usr/local/share/applications/axidev-osk.desktop
/usr/local/share/icons/hicolor/scalable/apps/axidev-osk.svg
```

The static Rust launcher finds its payload relative to its own location. It starts `/usr/bin/python3 -I`, adds only the payload's Python tree, then checks the host runtime before normal startup.

The runtime gate requires Python 3.10 or newer. It accepts matching PySide6 and Qt releases from 6.7 up to, but not including, 7.0. It also checks the Qt X11 and Wayland platform plugins and verifies that LayerShellQt resolves against the installed Qt libraries.

## Lifecycle

`install.sh` becomes `/usr/local/sbin/axidev-osk-install` after installation.

`install` verifies a local checksum or downloaded `SHA256SUMS` manifest. It extracts into a temporary `/opt/axidev-osk.new.*` directory and runs the payload's runtime check before activation.

Activation moves the current payload to `/opt/axidev-osk.old` and moves the staged payload into `/opt/axidev-osk`. A failed activation restores the previous payload.

`upgrade` downloads the latest installer, payload, and checksum manifest.

`rollback` swaps `/opt/axidev-osk` and `/opt/axidev-osk.old`.

`uninstall` removes active and rollback payloads plus owned integration files. It preserves the shared `uinput` group and memberships.

## Build And Release

Build and verify the payload through the pinned Docker environment:

```bash
python packaging/build.py linux payload
python packaging/build.py linux verify dist/linux/axidev-osk
```

Create release assets:

```bash
python packaging/build.py linux release
```

The release directory contains versioned and stable payload archives, versioned and stable repository source ZIPs, the lifecycle installer, and `SHA256SUMS`. The checksums detect corrupted downloads but do not authenticate the publisher because the assets and manifest use the same download channel.

`release-lock.json` records the supported architecture, minimum glibc version, pinned builder image, Rust toolchain, allowed host libraries, and virtual-machine images. Qt, PySide6, and LayerShellQt come from the host package manager, so the lock does not pin their artifacts.

## Interactive Linux Checks

The QEMU helper manages four profiles:

- `hyprland`: Arch Linux with Hyprland
- `kde`: Fedora with KDE Plasma
- `gnome`: Fedora with GNOME
- `lightdm-x11`: Arch Linux with LightDM, Xorg, and Xfce

Prepare, run, or reset a profile:

```bash
python packaging/build.py linux vm prepare hyprland
python packaging/build.py linux vm run hyprland
python packaging/build.py linux vm reset hyprland
```

Replace `hyprland` with `kde`, `gnome`, or `lightdm-x11`. The runner uses KVM when available and falls back to software emulation.

Every profile is a manual acceptance test. Run it with the GTK QEMU window visible and have a person verify the login screen or desktop, the rendered keyboard, and real key input. SSH access, successful cloud-init, an active service, or a running Axidev OSK process are diagnostics only; none of them make a profile pass. Automation may prepare the machine, open the window, and collect diagnostics, but the profile remains untested until the person using the window records the result.

## Other Packages

The Arch, Debian, RPM, and Nix definitions remain in tree. They are separate distribution integrations and do not define the standalone `/opt` payload.

## Windows

The unified release builder includes the stable source ZIP and Windows bootstrap. The bootstrap creates a Windows Python environment, then runs the trusted installer in [`windows/`](./windows/README.md).

The installer builds, locally signs, trusts, installs, and verifies a UIAccess executable under `C:\Program Files\Axidev OSK`. It also creates the current user's Start Menu shortcut. This remains a trusted local installer, not an officially signed end-user package.

A production-signed MSI with a registered uninstaller remains the intended public distribution format.
