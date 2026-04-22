# AxiDev OSK

A small on-screen keyboard built with PySide6 and Qt.

This version now sends key input through `axidev-io-python`. Until that package is released to PyPI, this repo keeps it as a git submodule under `vendor/axidev-io-python`.

The layout uses US legends on an ISO-style physical arrangement, including the extra `<` / `>` key next to the left Shift key.

## Run

```powershell
git submodule update --init --recursive
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .\vendor\axidev-io-python
pip install -e .
python -m axidev_osk
```

Or after installation:

```powershell
axidev-osk
```

## Notes

- The app initializes `axidev_io.keyboard` on startup and sends key events to the currently active window.
- `Shift` and `Caps` are sticky in the UI and affect the emitted character selection for printable keys.
- If `axidev-io-python` is not installed yet, the window stays open but the keyboard is disabled and the status line explains how to install the submodule package.

## Structure

- `src/axidev_osk/layouts/us_iso.py`: the US ISO keyboard layout definition.
- `src/axidev_osk/components/key_button.py`: the reusable key button factory and latch helpers.
- `src/axidev_osk/components/keyboard_widget.py`: the keyboard container that renders rows from the layout.
- `src/axidev_osk/keyboard_io.py`: the `axidev_io` bridge that initializes the backend and dispatches key presses.
- `src/axidev_osk/application/main_window.py`: the main Qt window.
- `src/axidev_osk/styles/theme.py`: the utilitarian stylesheet.
- `src/axidev_osk/app.py`: the application entrypoint.
