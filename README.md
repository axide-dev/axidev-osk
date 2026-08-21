# Axidev OSK

An OSK for Windows and Linux that stays out of your way.

Axidev OSK gives you a clean, always-on-top keyboard overlay you can pop up when you need it and hide when you don't. It works on Windows, KDE Plasma Wayland, wlroots-based compositors like `niri` and `Hyprland`, and X11.

## Features

- Always-on-top overlay that floats above your other windows
- Hot-corner gesture to quickly show or hide the keyboard
- Real key emission, so it works in any app that accepts keyboard input
- Modifier latching for comfortable one-finger typing
- Runs on Windows, X11, and Wayland

## Install

### Linux

Install the system dependencies for your distribution, then run the installer. The installer downloads the latest release bundle, places it under `/opt/axidev-osk/`, and sets up the udev rule needed to emit keystrokes.

**Fedora:**

```bash
sudo dnf install qt6-qtwayland layer-shell-qt python3-pyside6 \
    libinput systemd-libs libxkbcommon python3 curl tar
curl -L https://raw.githubusercontent.com/axide-dev/axidev-osk/main/packaging/linux/install.sh | sudo bash
```

**Arch:**

```bash
sudo pacman -S --needed qt6-wayland layer-shell-qt pyside6 \
    libinput systemd libxkbcommon python curl tar
curl -L https://raw.githubusercontent.com/axide-dev/axidev-osk/main/packaging/linux/install.sh | sudo bash
```

After installing, log out and back in once so the new `input` group membership takes effect, then run `axidev-osk`.

To uninstall:

```bash
sudo bash /opt/axidev-osk/packaging/linux/uninstall.sh
```

For a manual source-based install (development, custom layouts, or distributions not covered above), see [`packaging/MANUAL_INSTALL.md`](./packaging/MANUAL_INSTALL.md).

### Windows

Requirements: Windows 10 or newer, Python 3.10+, and PowerShell 5.1.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm 'https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-windows-install.ps1' | iex"
```

The installer downloads the latest release, installs Axidev OSK under
`C:\Program Files\Axidev OSK`, and adds it to the current user's Start Menu.
Windows asks for UAC approval because the development installer trusts a local
signing certificate and enables UIAccess.
See the [Windows install guide](./packaging/windows/README.md) for details.

To uninstall:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm 'https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-windows-install.ps1'))) -Uninstall"
```

A production-signed MSI remains planned for public distribution.

## Wayland Notes

The overlay works best on compositors that support the layer-shell protocol, such as:

- KDE Plasma Wayland
- `niri`
- `Hyprland`
- other wlroots-based compositors

On GNOME/Mutter the app falls back to its X11/XWayland overlay backend, since GNOME does not currently expose the layer-shell behavior the overlay wants.

On Linux, install the matching Qt layer-shell plugin (`layer-shell-qt` on most distributions) alongside the packages listed above to get proper overlay support.

On Wayland environments where layer-shell is unavailable or unsupported, the keyboard UI may be constrained by the compositor to the bounds of the application context that launched it. This is a display-surface limitation only: the input backend can still emit key events through the configured Linux input path.

## Project Status

Axidev OSK is usable today as a keyboard overlay, but the project is aimed at something bigger: a modular composition system for on-screen input surfaces, with multiple windows, reusable grids, and user-defined layouts driven by a Lua config.

What works now:

- a single main keyboard window
- US legends on an ISO-style physical arrangement
- modifier latch behavior
- always-on-top overlay behavior across Windows, X11, and supported Wayland compositors

What's planned:

- multiple independent windows and surfaces
- Lua-based user customization
- config-driven composition of grids and layouts
- more reusable grid and container primitives

## Contributing

Contributions are welcome. Changes should land through pull requests rather than direct pushes to `main`, even for small cleanups.

To work on the project, clone the repository with submodules:

```bash
git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
cd axidev-osk
```

From there, follow the platform-specific system package steps in the [Install](#install) section, skipping the `curl` and `unzip`/`Expand-Archive` commands.

For normal development, install the vendored input backend and this project into a local virtual environment. The project's Python dependencies come from `pyproject.toml`.

```bash
python -m venv .venv && .venv/bin/python -m pip install -e ./vendor/axidev-io-python -e .
```

To start the app from the checkout without relying on the installed entrypoint, use:

```bash
PYTHONPATH=src .venv/bin/python -m axidev_osk
```

Before making structural changes, please read [`AGENTS.md`](./AGENTS.md). It describes the modular architecture rules the project is following while the Lua configuration layer is being built.

PR guidance:

- keep each PR focused on one concern
- call out architectural impact when touching windows, grids, layouts, or orchestration
- note platform-specific behavior clearly when Windows, X11, or Wayland behavior changes

### Commit Style

Commits follow Conventional Commit-style subjects:

```text
type(scope): short imperative summary
```

Examples from the existing history:

- `fix(ui): add hot-corner window toggle and shared theme palette`
- `feat(release): add standalone app packaging`
- `refactor(ci): bump workflows to Python 3.14`

Use lowercase `type` and `scope`, keep the summary short, and prefer imperative phrasing (`add`, `fix`, `refactor`, `remove`).

## License

Axidev OSK is licensed under GPLv3. See [`LICENSE`](./LICENSE).
