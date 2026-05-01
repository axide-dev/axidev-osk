#!/usr/bin/env sh

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME=qt6ct QT_QUICK_CONTROLS_STYLE=Fusion QT_WAYLAND_SHELL_INTEGRATION=layer-shell AXIDEV_OSK_OVERLAY_BACKEND=wayland-layer-shell python -m axidev_osk
