#!/bin/sh
# Launcher shim installed to /usr/local/bin/axidev-osk.
#
# The application handles its own environment discovery (Wayland vs X11,
# layer-shell plugin lookup, etc.) so this shim only needs to invoke the
# application module with the venv Python. Avoid using the generated console
# script because its shebang contains the temporary staging path used during
# atomic upgrades.
exec /opt/axidev-osk/.venv/bin/python -m axidev_osk "$@"
