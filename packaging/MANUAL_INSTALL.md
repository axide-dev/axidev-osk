# Manual Installation

This document describes how to install Axidev OSK from source. It is meant for:

- developers working on the project
- users on distributions not yet covered by the system-wide installer
- anyone who wants to build a local virtual environment in their checkout instead of using `/opt`

For a normal install, follow the platform commands in the top-level [`README`](../README.md) instead.

## Linux

Install the system dependencies for your distribution. These are required by both the manual install and the system-wide install, because Qt6, PySide6, and layer-shell-qt are loaded from the system at runtime.

### Fedora

```bash
sudo dnf install qt6-qtwayland layer-shell-qt \
    libinput-devel systemd-devel systemd-libs \
    libxkbcommon-devel python3-devel
```

### Arch

```bash
sudo pacman -S --needed python qt6-wayland layer-shell-qt \
    libinput systemd libxkbcommon
```

### Build and install into a project-local virtual environment

```bash
curl -L -o axidev-osk-source.zip https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-source.zip
unzip axidev-osk-source.zip
cd axidev-osk
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ./vendor/axidev-io-python
python -m pip install -e .
axidev-osk
```

Or, when working from a clone:

```bash
git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
cd axidev-osk
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ./vendor/axidev-io-python
python -m pip install -e .
PYTHONPATH=src python -m axidev_osk
```

### One-time uinput permissions

Linux requires permission to emit keystrokes through `/dev/uinput`. Run the helper script bundled with the vendored input backend:

```bash
bash ./vendor/axidev-io-python/src/axidev_io/vendor/axidev-io/scripts/setup_uinput_permissions.sh
```

This installs a udev rule, ensures the `input` group exists, and adds your user to it. Log out and back in for the new group membership to take effect.

## Windows

Requirements: Python 3.10+

This source workflow cannot receive Windows UIAccess because it launches the
shared Python interpreter. Developers testing trusted topmost behavior should
use the [trusted Windows development install](./windows/README.md).

```powershell
curl -L -o axidev-osk-source.zip https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-source.zip
Expand-Archive -Path axidev-osk-source.zip -DestinationPath .
cd axidev-osk
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .\vendor\axidev-io-python
python -m pip install -e .
axidev-osk
```
