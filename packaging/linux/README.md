# Linux Installer Internals

This document describes what `install.sh` and `uninstall.sh` actually do, what files they touch, and how to debug a failed install.

For an architecture overview, see [`../README.md`](../README.md).

## What `install.sh` does

```
1. Re-exec with sudo if not already root.
2. Verify the host architecture (currently x86_64 only).
3. Verify required commands exist (curl, tar, python3, install, udevadm, ...).
4. Download axidev-osk-linux-x86_64.tar.gz from the latest release.
5. Extract to a temporary directory.
6. Stage the new install at /opt/axidev-osk.new/:
   - python3 -m venv --system-site-packages /opt/axidev-osk.new/.venv
   - pip install --no-index --no-deps the bundled wheels
   - import smoke test
7. Atomic swap: /opt/axidev-osk -> /opt/axidev-osk.old, then
                /opt/axidev-osk.new -> /opt/axidev-osk, then
                rm -rf /opt/axidev-osk.old.
8. Install /usr/local/bin/axidev-osk from the bundled launcher.
9. Ensure 'input' group exists.
10. Ensure /etc/udev/rules.d/70-axidev-io-uinput.rules has the expected
    contents; reload udev only if the rule actually changed.
11. Verify /dev/uinput is owned by group 'input' with mode 0660; modprobe
    if needed; warn if a reboot may be required.
12. Add the invoking user to the 'input' group if not already a member.
```

## Required system packages

These come from the distribution package manager. The installer does not attempt to install them; the top-level README documents the per-distro commands.

- `qt6-qtwayland` (Fedora) / `qt6-wayland` (Arch)
- `layer-shell-qt`
- `python3-pyside6` (Fedora) / `pyside6` (Arch)
- `libinput`, `systemd-libs` (libudev), `libxkbcommon`
- `python3` (>= 3.10), `curl`, `tar`

The `-devel` packages are not needed at install time because the C extension is precompiled in the release bundle.

## Files written

| Path | Owner | Mode | Source |
|------|-------|------|--------|
| `/opt/axidev-osk/` | root:root | 0755 | release bundle |
| `/usr/local/bin/axidev-osk` | root:root | 0755 | `resources/launcher.sh` |
| `/etc/udev/rules.d/70-axidev-io-uinput.rules` | root:root | 0644 | `resources/70-axidev-io-uinput.rules` |

## Files NOT written

The installer does not create or modify:

- any per-user configuration or state directory
- any `.desktop` file or icon
- any systemd unit
- any file outside `/opt/axidev-osk/`, `/usr/local/bin/`, and `/etc/udev/rules.d/`

## Debugging a failed install

**Download fails.** The script aborts before touching anything. The previous install (if any) is still in place.

**`pip install` fails inside the staging venv.** The script aborts before the swap. `/opt/axidev-osk/` is unchanged. The temporary `/opt/axidev-osk.new/` is removed by the EXIT trap.

**Import smoke test fails.** Same as above; the swap never happens.

**Atomic swap interrupted.** If the script is killed between `mv /opt/axidev-osk /opt/axidev-osk.old` and `mv /opt/axidev-osk.new /opt/axidev-osk`, the install is in a half state. Recovery: `mv /opt/axidev-osk.old /opt/axidev-osk` (or simply re-run the installer, which will detect a missing `/opt/axidev-osk` and proceed cleanly).

**`/dev/uinput` still wrong after install.** The kernel module may not be loaded (`modprobe uinput`), or the udev rule may need a reboot to take effect on some setups. The launcher will fail with a permission error in that case. Confirm with:

```bash
stat -c '%a %G' /dev/uinput   # expected: 660 input
groups                        # should include 'input' after logout/login
```

## What `uninstall.sh` does

```
1. Re-exec with sudo if not already root.
2. rm -rf /opt/axidev-osk
3. rm -f /usr/local/bin/axidev-osk
4. rm -f /etc/udev/rules.d/70-axidev-io-uinput.rules
5. udevadm control --reload-rules
```

The script does not remove the user from the `input` group. That group exists on most systems independently of this application and may be used by other software.

## Re-running `install.sh`

`install.sh` is safe to re-run. The bundle is downloaded fresh and `/opt/axidev-osk` is replaced via the atomic swap. The udev rule and group membership steps detect their desired state and only act if a change is needed.
