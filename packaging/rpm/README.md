# RPM Packaging

This directory contains the Fedora/RPM packaging recipe for Axidev OSK.

The spec builds both packages from the release source archive:

- `axidev-io` from `vendor/axidev-io-python`
- `axidev-osk` from the repository root

`axidev-io` is bundled in this RPM for now. The intended long-term shape is a separate `python3-axidev-io` package once `axidev-io` is published independently.

## Local Build

From a source tree matching the release archive layout:

```bash
sudo dnf install rpm-build pyproject-rpm-macros python3-devel gcc \
    libinput-devel systemd-devel libxkbcommon-devel
rpmbuild -ba packaging/rpm/axidev-osk.spec
```

For clean Fedora builds, use `mock`:

```bash
sudo dnf install mock
mock -r fedora-rawhide-x86_64 packaging/rpm/axidev-osk.spec
```

## Runtime Dependencies

The RPM depends on distro-provided Qt/PySide/layer-shell packages instead of bundling them. This is intentional: PySide6, Qt6, and layer-shell-qt need to come from the same system ABI family to avoid plugin crashes.

## uinput Permissions

The RPM installs `70-axidev-io-uinput.rules` and reloads udev in `%post`. Users run `axidev-osk linux setup-permissions` to join the dedicated `uinput` group before emitting events through `/dev/uinput`.
