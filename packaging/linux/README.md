Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode.
Every call here is inayayousfi's, and no agent acted on its own.

# Linux Distribution Internals

This document describes the standalone Linux payload, its lifecycle installer, release signing, and interactive test environments.

## Supported Host

The payload targets x86_64 Linux with glibc 2.34 or newer. It requires `/usr/bin/python3` version 3.10 or newer.

The host supplies PySide6, Qt, Qt's X11 and Wayland platform plugins, LayerShellQt, libinput, libudev, libxkbcommon, and normal desktop libraries. PySide6 and Qt must use matching major and minor versions from 6.7 up to, but not including, 7.0.

Use these runtime packages on Fedora:

```bash
sudo dnf install python3 python3-pyside6 qt6-qtwayland layer-shell-qt \
    libinput systemd-libs libxkbcommon
```

Use these runtime packages on Arch Linux:

```bash
sudo pacman -S --needed python pyside6 qt6-wayland layer-shell-qt \
    libinput systemd libxkbcommon
```

The allowed native input-library sonames are recorded in `release-lock.json`.

## Payload Contents

```text
axidev-osk/
  bin/axidev-osk
  lib/python/
  libexec/launch.py
  share/applications/axidev-osk.desktop
  share/icons/hicolor/scalable/apps/axidev-osk.svg
  share/licenses/
  release.json
```

The payload's Python tree contains Axidev OSK and the native `axidev_io` extension. It does not contain PySide6, Qt, or LayerShellQt.

The launcher is a static Rust executable. It resolves the payload from its own path and starts `/usr/bin/python3 -I`.

`launch.py` rejects Python older than 3.10. Before normal startup or `--verify-runtime`, it checks the PySide6 and Qt range, matching major and minor versions, Qt's X11 and Wayland platform plugins, and LayerShellQt compatibility. Runtime verification then reports the resolved versions and plugin paths.

`release.json` records the payload version, architecture, minimum glibc version, host-runtime requirements, and the SHA-256 digest of every regular file.

## Building

Run the root command from the repository checkout:

```bash
python build.py linux payload
```

The outer command builds the pinned manylinux Docker image. Docker writes the result to the `axidev-osk-linux-output` volume, and the build command copies the verified payload into the requested output directory.

The inner build performs these steps:

1. Build the vendored input backend wheel.
2. Build the Axidev OSK wheel.
3. Install both wheels into the payload's Python tree without dependencies or bytecode.
4. Build the static Rust launcher.
5. Install desktop resources, icons, licenses, and metadata.
6. Verify file checksums, launcher linkage, native input dependencies, and the host-library allowlist.

The default output is `dist/linux/axidev-osk`.

Verify an existing payload again with:

```bash
python build.py linux verify dist/linux/axidev-osk
```

Static verification does not import host Qt packages. The launcher's `--verify-runtime` check covers those packages on the target system.

## Installing A Local Build

Build and install the current checkout with:

```bash
sudo ./packaging/linux/install-from-source.sh
```

The script builds the payload, archives it, calculates its checksum, and calls `install.sh` with that local archive.

A local payload requires a checksum but does not require Minisign. Downloaded releases always require the signed manifest.

## Release Signing

Create release assets with:

```bash
python build.py linux release --signing-key /path/to/minisign.key
```

The command requires a public key at `packaging/linux/minisign.pub`. The private key must match that public key.

The command creates:

```text
release-assets/
  axidev-osk-VERSION-linux-x86_64.tar.gz
  axidev-osk-linux-x86_64.tar.gz
  axidev-osk-VERSION-source.zip
  axidev-osk-source.zip
  axidev-osk-install
  SHA256SUMS
  SHA256SUMS.minisig
```

The repository ZIP includes tracked files and vendored submodule contents.

GitHub Actions reads the passwordless private key from `MINISIGN_SECRET_KEY`, writes it to a temporary mode-restricted file, signs the manifest, deletes the key file, and uploads one asset set.

Signing is not provisioned until the repository public key and matching GitHub secret exist. Release builds fail instead of publishing unsigned assets.

## Lifecycle Commands

Install the latest signed release:

```bash
sudo axidev-osk-install install
```

Upgrade to the latest signed release:

```bash
sudo axidev-osk-install upgrade
```

Swap active and retained payloads:

```bash
sudo axidev-osk-install rollback
```

Remove Axidev OSK:

```bash
sudo axidev-osk-install uninstall
```

The first downloaded installer must be saved to a file and run from that file. A pipe cannot install the lifecycle command because no installer file would remain to copy.

## Failure Behavior

A bad signature or checksum stops before extraction.

An unsafe archive path stops before extraction.

A failed staged runtime check leaves the active payload unchanged and removes the temporary staging directory.

A failed activation restores the retained payload.

The installer keeps the previous successful payload at `/opt/axidev-osk.old` until another install replaces it.

Rollback warns if the retained payload fails runtime verification, but it leaves the swap complete so the operator can inspect or reverse it.

Uninstall stops when permission or autostart cleanup fails. `uninstall --force` removes owned files after reporting incomplete cleanup.

## Files Owned

```text
/opt/axidev-osk/
/opt/axidev-osk.old/
/usr/local/bin/axidev-osk
/usr/local/sbin/axidev-osk-install
/usr/local/share/applications/axidev-osk.desktop
/usr/local/share/icons/hicolor/scalable/apps/axidev-osk.svg
```

Permission setup manages `/etc/modules-load.d/axidev-osk-uinput.conf` and `/etc/udev/rules.d/70-axidev-io-uinput.rules` through the application command line. Removal deletes only files whose contents still match Axidev OSK's definitions, and it does not unload the shared `uinput` module. Autostart setup manages the selected user's XDG autostart file.

The uninstaller does not remove the shared `uinput` group or its memberships.

## QEMU Profiles

Prepare one profile from a verified local payload:

```bash
python build.py linux vm prepare hyprland \
    --payload dist/linux/axidev-osk
```

Run the prepared profile:

```bash
python build.py linux vm run hyprland
```

Reset its writable disk and cached installer source:

```bash
python build.py linux vm reset hyprland
```

Available profiles are `hyprland`, `kde`, and `gnome`. Preparation downloads a checksum-pinned cloud image, archives the selected payload, calculates its checksum, caches a local installer source, and generates cloud-init data.

QEMU exposes the cached source through a read-only 9p device during provisioning. Cloud-init mounts it temporarily, runs the lifecycle installer, and unmounts it before reboot. The installed application runs from `/opt/axidev-osk` through `/usr/local/bin/axidev-osk`; the guest does not retain a host payload mount.

Hyprland starts Axidev OSK through its compositor configuration. KDE and GNOME provisioning create the selected user's XDG autostart entry through the installed application command line.

The runner opens a GTK QEMU window. It uses KVM when `/dev/kvm` is accessible and otherwise uses slower software emulation.

QEMU testing is interactive. It verifies the installer, host package set, and compositor behavior that static container checks cannot observe.
