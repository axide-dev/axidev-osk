Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode.
Every call here is inayayousfi's, and no agent acted on its own.

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

The Linux release carries Axidev OSK, its native input extension, and a static launcher. The host must provide x86_64 Linux, glibc 2.34 or newer, Python 3.10 or newer, PySide6 and Qt from the same 6.7-or-newer release below 7.0, Qt's X11 and Wayland plugins, LayerShellQt, and the normal desktop input libraries.

**Fedora:**

```bash
sudo dnf install python3 python3-pyside6 qt6-qtwayland layer-shell-qt \
    libinput systemd-libs libxkbcommon curl tar minisign
```

**Arch:**

```bash
sudo pacman -S --needed python pyside6 qt6-wayland layer-shell-qt \
    libinput systemd libxkbcommon curl tar minisign
```

Download and run the lifecycle installer:

```bash
curl --fail --location --remote-name \
    https://github.com/axide-dev/axidev-osk/releases/latest/download/axidev-osk-install
chmod +x axidev-osk-install
sudo ./axidev-osk-install install
```

The installer verifies the signed release manifest and payload before changing `/opt/axidev-osk`. Log out and back in after installation if the installer adds you to the `uinput` group.

The installed lifecycle command supports upgrades, rollback, and removal:

```bash
sudo axidev-osk-install upgrade
sudo axidev-osk-install rollback
sudo axidev-osk-install uninstall
```

For a manual source installation, see [`packaging/MANUAL_INSTALL.md`](./packaging/MANUAL_INSTALL.md).

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

## Command Line

Running `axidev-osk` without arguments starts the keyboard. Passing an argument selects the command line without starting the graphical runtime.

Linux permission commands default to the invoking user. Administrators can prepare another local account with `--user NAME`.

```bash
axidev-osk linux setup-permissions
axidev-osk linux status-permissions
axidev-osk linux remove-permissions
```

Permission setup creates a dedicated `uinput` group, installs the udev rule, and adds the selected user. Log out and back in after a new membership is added. Permission removal disables the Axidev OSK rule but preserves the shared group and its memberships.

Linux autostart uses the desktop-session XDG autostart standard. It starts the current visible keyboard after the selected user logs into a graphical desktop.

```bash
axidev-osk linux setup-autostart
axidev-osk linux status-autostart
axidev-osk linux remove-autostart
```

Login-screen startup is separate from user autostart. Axidev OSK supports Plasma Login Manager, greetd, and LightDM.

```bash
axidev-osk linux setup-greeter
axidev-osk linux status-greeter
axidev-osk linux remove-greeter
```

`setup-greeter` shows an arrow-key menu of installed supported managers. Scripts can select one directly with `--manager plasma-login`, `--manager greetd`, or `--manager lightdm`. Setup checks the selected manager and its current configuration before writing files. It does not restart the display manager, so reboot or restart it after setup.

Plasma Login Manager and LightDM use their own greeter startup hooks. The greetd adapter saves and wraps the existing default-session command. It starts that command before Axidev OSK, keeps the greeter authoritative, and restores the exact command during removal.

The keyboard retries with exponential backoff while the greeter remains active. A keyboard or display-detection failure never stops the greeter. Failures appear in the system journal under `axidev-osk-greeter`.

Greeter setup adds the manager's service account to the shared `uinput` group. Removal preserves that membership, matching the normal permission cleanup policy.

On Windows, replacing `osk.exe` or another protected system binary is not supported. Future Windows integration should use supported accessibility registration and startup mechanisms.

## Wayland Notes

The overlay works best on compositors that support the layer-shell protocol:

- KDE Plasma Wayland
- `niri`
- `Hyprland`
- other wlroots-based compositors

On GNOME and Mutter, the app does not request layer-shell behavior. It uses the regular Qt window path instead.

The Linux payload uses the host's Qt Wayland and LayerShellQt components. Its launcher checks the Python, PySide6, Qt, platform plugin, and LayerShellQt versions before startup. PySide6 and Qt must have matching major and minor versions.

Without layer-shell support, the compositor can constrain the keyboard to regular application-window behavior. The configured Linux input backend can still emit key events.

## Project Status

Axidev OSK is usable today as a keyboard overlay, but the project is aimed at a modular composition system with multiple windows, reusable grids, and Lua-driven layouts.

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

Changes should land through pull requests rather than direct pushes to `main`.

Clone the repository with submodules:

```bash
git clone --recurse-submodules https://github.com/axide-dev/axidev-osk.git
cd axidev-osk
```

For normal development, install the vendored input backend and this project into a local virtual environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ./vendor/axidev-io-python -e .
```

Start the app from the checkout:

```bash
PYTHONPATH=src .venv/bin/python -m axidev_osk
```

Read [`AGENTS.md`](./AGENTS.md) before structural changes. It documents the modular architecture rules.

PR guidance:

- keep each PR focused on one concern
- call out architectural impact when changing windows, grids, layouts, or orchestration
- note platform-specific behavior when Windows, X11, or Wayland changes

### Commit Style

Commits use this subject format:

```text
type(scope): short imperative summary
```

Use lowercase `type` and `scope`. Keep the summary short and imperative.

## License

Axidev OSK is licensed under GPLv3. See [`LICENSE`](./LICENSE).
