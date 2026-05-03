# Debian Packaging

This directory contains a Debian packaging template under `debian/`.

The package builds both wheels from source:

- `axidev-io` from `vendor/axidev-io-python`
- `axidev-osk` from the repository root

`axidev-io` is bundled for now. The intended long-term shape is a separate `python3-axidev-io` package once it is independently published.

## Local Build

Debian tooling expects the `debian/` directory at the source root. From a clean source tree:

```bash
cp -a packaging/deb/debian ./debian
sudo apt install debhelper dh-python python3-all-dev python3-build \
    python3-installer python3-setuptools python3-wheel gcc pkg-config \
    libinput-dev libudev-dev libxkbcommon-dev
dpkg-buildpackage -us -uc
```

## Runtime Dependencies

The package depends on system `python3-pyside6`, `qt6-wayland`, and `layer-shell-qt`. They are intentionally not bundled so PySide6, Qt6, and layer-shell-qt come from the same ABI family.

## uinput Permissions

The post-install script ensures the `input` group exists, reloads udev, and reminds the user to join the `input` group. It does not choose a desktop user automatically because package maintainer scripts run as root without reliable user context.
