# Axidev OSK

An on-screen keyboard for Windows and Linux that stays out of your way.

Axidev OSK gives you a clean, always-on-top keyboard overlay you can pop up when you need it and hide when you don't. It works on Windows, KDE Plasma Wayland, wlroots-based compositors like `niri` and `Hyprland`, and X11.

## Features

- Always-on-top overlay that floats above your other windows
- Hot-corner gesture to quickly show or hide the keyboard
- Real key emission, so it works in any app that accepts keyboard input
- Modifier latching for comfortable one-finger typing
- Runs on Windows, X11, and Wayland

## Install

Axidev OSK is installed from source into a Python virtual environment. The commands below download the latest release source archive (no `git` required) and install from it. The archive already bundles the vendored `axidev-io-python` sources.

### Windows

Requirements: Python 3.10+

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

### Fedora (Wayland)

```bash
sudo dnf install python3-pyside6 qt6-qtwayland layer-shell-qt \
    libinput-devel systemd-devel systemd-libs \
    libxkbcommon-devel python3-devel

curl -L -o axidev-osk-source.zip https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-source.zip
unzip axidev-osk-source.zip
cd axidev-osk
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ./vendor/axidev-io-python --no-deps
python -m pip install -e . --no-deps
axidev-osk
```

### Arch (Wayland)

```bash
sudo pacman -S --needed python python-pyside6 qt6-wayland layer-shell-qt \
    libinput systemd libxkbcommon

curl -L -o axidev-osk-source.zip https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-source.zip
unzip axidev-osk-source.zip
cd axidev-osk
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ./vendor/axidev-io-python --no-deps
python -m pip install -e . --no-deps
axidev-osk
```

### Linux: one-time uinput setup

Linux needs permission to emit keystrokes through `uinput`. The first time you run the app, it will tell you if permissions are missing and point you at a helper script.

You can also run the helper directly from the vendored sources:

```bash
bash ./vendor/axidev-io-python/src/axidev_io/vendor/axidev-io/scripts/setup_uinput_permissions.sh
```

The app also offers an **Open In Terminal** option so the helper can run in a real terminal with a normal `sudo` prompt.

## Wayland Notes

The overlay works best on compositors that support the layer-shell protocol, such as:

- KDE Plasma Wayland
- `niri`
- `Hyprland`
- other wlroots-based compositors

On GNOME/Mutter the app falls back to its X11/XWayland overlay backend, since GNOME does not currently expose the layer-shell behavior the overlay wants.

On Linux, install the matching Qt layer-shell plugin (`layer-shell-qt` on most distributions) alongside the packages listed above to get proper overlay support.

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

From there, follow the platform-specific venv and `pip install -e` steps in the [Install](#install) section, skipping the `curl` and `unzip`/`Expand-Archive` commands.

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
