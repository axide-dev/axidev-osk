# Axidev OSK

An on-screen keyboard for Windows and Linux that stays out of your way.

Axidev OSK gives you a clean, always-on-top keyboard overlay you can pop up when you need it and hide when you don't. It works on Windows, KDE Plasma Wayland, wlroots-based compositors like `niri` and `Hyprland`, and X11.

## Features

- Always-on-top overlay that floats above your other windows
- Hot-corner gesture to quickly show or hide the keyboard
- Real key emission, so it works in any app that accepts keyboard input
- Modifier latching for comfortable one-finger typing
- Runs on Windows, X11, and Wayland
- Standalone bundles available, no Python setup needed

## Install

The easiest way to try Axidev OSK is to grab a prebuilt bundle from the [Releases page](https://github.com/axide-dev/axidev-osk/releases).

- **Windows:** download `axidev-osk-<version>-windows-x64.zip`, extract it, and run `axidev-osk.exe`.
- **Linux:** download `axidev-osk-<version>-linux-x64.zip`, extract it, and run `axidev-osk`.

### Linux: one-time setup

Linux needs permission to emit keystrokes through `uinput`. The first time you run the app, it will tell you if permissions are missing and point you at a helper script.

You can also run the helper directly from the extracted bundle:

```bash
bash ./setup_uinput_permissions.sh
```

The app also offers an **Open In Terminal** option so the helper can run in a real terminal with a normal `sudo` prompt.

### Linux: runtime dependencies

Standalone Linux bundles need these libraries present on your system:

- `libinput`
- `libudev` (usually shipped as part of `systemd`)
- `xkbcommon`

Most modern Linux distributions already have these installed.

## Install From Source

If you want to hack on Axidev OSK or run the latest development version, you can install it from source.

### Windows

Requirements: Python 3.10+

```powershell
git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
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

git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
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

git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
cd axidev-osk
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ./vendor/axidev-io-python --no-deps
python -m pip install -e . --no-deps
axidev-osk
```

## Wayland Notes

The overlay works best on compositors that support the layer-shell protocol, such as:

- KDE Plasma Wayland
- `niri`
- `Hyprland`
- other wlroots-based compositors

On GNOME/Mutter the app falls back to its X11/XWayland overlay backend, since GNOME does not currently expose the layer-shell behavior the overlay wants.

Linux standalone bundles ship the matching Qt layer-shell plugin, so you don't need to install `layer-shell-qt` separately just to get overlay support.

## Project Status

Axidev OSK is usable today as a keyboard overlay, but the project is aimed at something bigger: a modular composition system for on-screen input surfaces, with multiple windows, reusable grids, and user-defined layouts driven by a Lua config.

What works now:

- a single main keyboard window
- US legends on an ISO-style physical arrangement
- modifier latch behavior
- always-on-top overlay behavior across Windows, X11, and supported Wayland compositors
- standalone packaging for Windows and Linux

What's planned:

- multiple independent windows and surfaces
- Lua-based user customization
- config-driven composition of grids and layouts
- more reusable grid and container primitives

## Contributing

Contributions are welcome. Changes should land through pull requests rather than direct pushes to `main`, even for small cleanups.

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
