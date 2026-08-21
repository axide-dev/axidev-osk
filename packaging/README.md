# Packaging

This directory holds everything related to distributing Axidev OSK to end users: install scripts, native package recipes, and platform-specific resources.

The repository deliberately keeps these files in tree even when no public package has been published yet. They are the source of truth for how the project is meant to be installed, and they need to evolve alongside the application code.

## Layout

```
packaging/
  README.md              # this file: install architecture overview
  MANUAL_INSTALL.md      # source-based install for development or unsupported distros
  arch/                  # Arch PKGBUILD and install hook
  deb/                   # Debian packaging template
  linux/
    README.md            # Linux installer internals
    install.sh           # system-wide installer (downloads latest release bundle)
    install-from-source.sh            # system-wide installer from a local checkout
    uninstall.sh         # cleanly removes the system-wide install
    resources/
      launcher.sh                     # placed at /usr/local/bin/axidev-osk
      70-axidev-io-uinput.rules       # placed at /etc/udev/rules.d/...
  windows/                # trusted local UIAccess development install
  nix/                   # NixOS module documentation
  rpm/                   # Fedora/RPM spec
```

The top-level `flake.nix` exposes the Nix package and NixOS module because Nix users expect flakes at the repository root.

## Installation Architecture

### Linux

A normal install ends up looking like this on disk:

```
/opt/axidev-osk/                         # entire install lives here
  .venv/                                 # virtual environment with --system-site-packages
  packaging/linux/uninstall.sh           # bundled uninstaller
  packaging/linux/resources/...          # source for the launcher and udev rule
  ...
/usr/local/bin/axidev-osk                # launcher shim that exec's the venv entry point
/etc/udev/rules.d/70-axidev-io-uinput.rules
```

The install path is intentionally simple:

- **Everything the application owns lives under `/opt/axidev-osk/`.** Wiping that directory removes the program. There is no per-user data managed by the installer at this stage.
- **The launcher in `/usr/local/bin/`** is a one-line shim that exec's `/opt/axidev-osk/.venv/bin/python -m axidev_osk`. The application performs its own environment discovery (Wayland vs X11, layer-shell plugin location, etc.); the shim does not pass extra environment variables.
- **The udev rule** allows non-root processes to write to `/dev/uinput` when they belong to the `input` group. The installer adds the invoking user to the `input` group when it is missing.

PySide6, Qt6, layer-shell-qt, libinput, libudev, and libxkbcommon are **not** bundled with the install. They are loaded from the system at runtime so that the Qt and layer-shell-qt versions match (a mismatch causes hard-to-diagnose ABI segfaults). The Linux dependency list lives in `linux/README.md` and in the top-level `README.md` install commands.

### Upgrade flow

`install.sh` performs the install atomically:

1. Stage the new install at `/opt/axidev-osk.new/`.
2. Run a Python import smoke test inside the staged venv.
3. Only on success: `mv /opt/axidev-osk /opt/axidev-osk.old` then `mv /opt/axidev-osk.new /opt/axidev-osk` then `rm -rf /opt/axidev-osk.old`.

If anything fails before the swap, the previous install remains untouched and `axidev-osk` keeps working from the old `/opt/axidev-osk/`.

### Idempotency

Re-running `install.sh` on a system that already has the correct configuration touches only what needs to change:

- The `/opt/axidev-osk/` swap always happens (the new release replaces the old).
- The `input` group is created only if missing.
- The udev rule file is rewritten only if its contents differ from the expected value.
- `udevadm` is reloaded only when the rule actually changed.
- The user is added to the `input` group only if not already a member.

### Uninstall

`/opt/axidev-osk/packaging/linux/uninstall.sh` removes `/opt/axidev-osk/`, `/usr/local/bin/axidev-osk`, and the udev rule. It does **not** touch the user's `input` group membership, since that group is shared with other parts of the system.

## Windows

The trusted local development flow lives in [`windows/`](./windows/README.md).
It builds, signs, trusts, installs, and verifies a UIAccess executable under
`C:\Program Files\Axidev OSK`. It does not produce an end-user installer.

The intended distribution shape remains:

- A signed MSI, likely built with WiX, that installs under `C:\Program Files\Axidev OSK\`.
- A Start Menu entry and an optional "Start at login" toggle that registers the launcher with the Windows startup mechanism.
- An uninstaller registered with Windows so the program shows up in *Apps & Features* and can be cleanly removed.

For now, Windows users follow the manual install in [`MANUAL_INSTALL.md`](./MANUAL_INSTALL.md).

## Manual / source install

For development, custom layouts, or distros not yet covered by a packaged install, see [`MANUAL_INSTALL.md`](./MANUAL_INSTALL.md). It documents the per-distro source-based flow that creates a virtual environment in the project checkout. This route is supported but not the recommended path for normal users.
