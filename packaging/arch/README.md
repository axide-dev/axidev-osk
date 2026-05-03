# Arch Packaging

This directory contains an Arch `PKGBUILD` and install hook.

The same `PKGBUILD` shape can be used locally, in the AUR, or as a starting point if the package is ever adopted into the official Arch repositories.

## Local Build

```bash
makepkg -Csf
sudo pacman -U axidev-osk-*.pkg.tar.zst
```

## Runtime Dependencies

The package depends on system `pyside6`, `qt6-wayland`, and `layer-shell-qt`. They are intentionally not bundled so the Qt ABI used by PySide6 and layer-shell-qt stays compatible.

## uinput Permissions

The install hook reloads udev and reminds the user to join the `input` group. It does not add a user automatically because package hooks do not reliably know which desktop user should receive input-device permissions.
