# Axidev OSK

Axidev OSK is a PySide6-based on-screen keyboard intended to become a modular desktop input surface rather than a single hardcoded keyboard window.

Today the project ships a working keyboard overlay with:

- a reusable `KeySpec` model for describing keys
- a grid-based `KeyboardWidget` that renders from layout data
- `axidev-io-python` integration for real key emission
- overlay/window placement support for Windows, X11, and Wayland
- a hot-corner controller to hide and restore visible app windows

The long-term direction is larger than the current implementation: windows should be composable, grids should be reusable building blocks, and one main process should orchestrate multiple surfaces that will eventually be described by a Lua config.

## Why This Project Exists

Most on-screen keyboards are delivered as one fixed application with one fixed layout. This project is aiming for a different model:

- UI pieces should be reusable components
- keyboard layouts should be data, not hardcoded widget trees
- windows should be swappable and composable
- the app should support multiple windows, not just one
- future user customization should come from configuration instead of code edits

That configuration layer is not implemented yet, but the codebase should keep moving in that direction.

## Current Architecture

The repository already has a useful split between data, UI components, and application shell:

- `src/axidev_osk/models.py`
  Defines `KeySpec` and `KeyDisplay`, the data model used to describe keys and display variants.
- `src/axidev_osk/layouts/`
  Holds layout builders such as `build_us_iso_layout()`, which returns structured key definitions.
- `src/axidev_osk/components/`
  Contains reusable UI pieces such as `KeyboardWidget`, `KeyButton`, and the key interaction state machine.
- `src/axidev_osk/application/`
  Contains windowing and shell concerns such as overlay behavior, chrome, layer-shell support, and hot-corner toggling.
- `src/axidev_osk/keyboard_io.py`
  Adapts UI key events to `axidev_io` so input emission stays separate from presentation.
- `src/axidev_osk/app.py`
  Wires the application together and launches the current main window.

This is the base we should keep extending instead of collapsing back into one monolithic window class.

## Target Architecture

The intended architecture is:

1. One main process owns the application lifecycle and window orchestration.
2. Windows are reusable surfaces, not special-case one-off screens.
3. Grids are reusable composition units that can host buttons or other controls.
4. Buttons and controls are componentized so they can be reused across layouts and windows.
5. Layouts are defined as data and can later be produced from Lua configuration.
6. Multiple windows and multiple layouts must be considered a first-class use case.

In practice, that means new work should prefer:

- data-driven definitions over hardcoded widget placement
- composition over subclass sprawl
- isolated controllers/services over window-owned business logic
- APIs that can support more than one window instance

## Project Status

Implemented now:

- single main keyboard window
- US legends on an ISO-style physical arrangement
- modifier latch behavior
- always-on-top overlay behavior across major desktop environments
- stand-alone packaging script

Planned direction:

- multiple independent windows/surfaces
- config-driven composition
- Lua-based user customization
- more reusable grid/container primitives
- layouts that are selected and assembled at runtime

## Getting Started

### Development install

```powershell
git submodule update --init --recursive
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .\vendor\axidev-io-python
python -m pip install -e .
python -m axidev_osk
```

After installation, you can also run:

```powershell
axidev-osk
```

### Linux and Wayland notes

Linux keyboard injection requires `uinput` access. If permission setup has not been applied yet, the app will explain how to run the bundled setup script.

In standalone Linux bundles, that helper is shipped at the top level of the extracted app folder as `setup_uinput_permissions.sh` so it can be run directly from a terminal:

```bash
bash ./setup_uinput_permissions.sh
```

The app also offers an `Open In Terminal` path on Linux so the bundled helper can run in a real terminal window with a normal `sudo` prompt.

For Wayland layer-shell support, install a Qt layer-shell plugin first. On Fedora:

```bash
sudo dnf install layer-shell-qt
```

Then launch from a real Wayland session.

## Packaging

Standalone builds are produced by [`scripts/build_standalone.py`](/C:/Users/ziede/code/axidev-osk/scripts/build_standalone.py).

Published archives follow this naming pattern:

- `axidev-osk-<version>-windows-x64.zip`
- `axidev-osk-<version>-linux-x64.zip`

Linux bundles still depend on system `libinput`, `libudev`, and `xkbcommon` at runtime. Wayland layer-shell behavior also depends on a compatible shell-integration plugin such as KDE's `layer-shell-qt`.

## Contributor Guidance

Before changing structure-heavy code, read [`AGENTS.md`](/C:/Users/ziede/code/axidev-osk/AGENTS.md). It records the modular architecture rules this project is supposed to follow while the Lua configuration layer is still being built.

## Contributing

This project is in a relatively stable state now, so changes should preferably land through pull requests rather than direct pushes.

Preferred workflow:

- create a focused branch for each change
- open a PR for review, even for small cleanups
- keep PRs scoped to one concern when possible
- avoid mixing architecture changes, UI changes, and packaging changes in one PR unless they are tightly coupled

### Commit Style

The existing history is mostly following a Conventional Commit-style subject line, and new commits should keep that format.

Preferred pattern:

```text
type(scope): short imperative summary
```

Examples already used in this repository:

- `fix(ui): add hot-corner window toggle and shared theme palette`
- `feat(release): add standalone app packaging`
- `refactor(ci): bump workflows to Python 3.14`

Guidelines:

- use lowercase `type` and `scope`
- keep the summary short and specific
- prefer scopes such as `ui`, `release`, `ci`, or another concrete subsystem
- use imperative phrasing like `add`, `remove`, `refactor`, `fix`

## License

This project is licensed under GPLv3. See [`LICENSE`](/C:/Users/ziede/code/axidev-osk/LICENSE).
