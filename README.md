# AxiDev OSK

A small on-screen keyboard shell built with PySide6 and Qt.

This version is focused on UX structure only. The window contains just the keyboard, and the key control is exposed as a reusable `create_key_button(...)` function for later behavior work.

The layout uses US legends on an ISO-style physical arrangement, including the extra `<` / `>` key next to the left Shift key.

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m axidev_osk
```

Or after installation:

```powershell
axidev-osk
```

## Notes

- The keyboard is currently presentation-focused and does not type into external widgets yet.
- `Shift` and `Caps` are wired as latchable examples so the button factory already supports latched state and separate latch/unlatch callbacks.
