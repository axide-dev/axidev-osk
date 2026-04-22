# Axidev OSK

A small on-screen keyboard built with PySide6 and Qt.

It sends key input through `axidev-io-python`. Until that package is released to PyPI, this repo keeps it as a git submodule under `vendor/axidev-io-python`.

The layout uses US legends on an ISO-style physical arrangement, including the extra `\` / `|` key next to the left Shift key.

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

## Wayland Layer-Shell

On Fedora, install the Qt layer-shell plugin first:

```bash
sudo dnf install layer-shell-qt
```

Then run the app from a real Wayland desktop session:

```bash
. .venv/bin/activate
python -m axidev_osk
```

## Releases

Published releases now ship a single stand-alone archive per platform:

- `axidev-osk-<version>-windows-x64.zip`
- `axidev-osk-<version>-linux-x64.zip`

Each archive contains the runnable app plus the bundled Python runtime and the
required license/compliance files. Linux builds still rely on the system
`libinput`, `libudev`, and `xkbcommon` shared libraries at runtime.
Wayland layer-shell support also requires a Qt `layer-shell` shell-integration
plugin such as KDE's `layer-shell-qt`.

## License

This project is licensed under GPLv3. See `LICENSE`.
