---
name: reload-plasma-input-method
description: ALWAYS use this skill when reloading or activating an installed Axidev OSK build inside a native KDE Plasma Wayland session without logging out or restarting KWin. It safely replaces the KWin-owned lock-screen supervisor and the ordinary autostart process after `/opt/axidev-osk` changes.
---

# Reload Axidev OSK On Plasma

Use this workflow after installing or replacing `/opt/axidev-osk` on native
KDE Plasma. Linux keeps running processes attached to the old files, even when
their command line still names `/opt/axidev-osk`.

The secure input method and the ordinary desktop application have separate
owners. Reload and verify both.

## Safety Rules

- Use this workflow only on native Linux under a KDE Plasma Wayland session.
- Do not restart KWin, Plasma, or the user session.
- Do not change `kwinrc` or create a temporary input-method desktop file. KWin
  6.7.5 stored that change but did not replace the running process.
- Do not select a process with `pgrep` alone. Identify the secure supervisor
  through its D-Bus service, then verify its executable and command line.
- Do not kill the Python worker directly. Its supervisor owns its lifecycle.
- Do not use `SIGTERM` or a normal exit. KWin recreates the privileged Wayland
  connection through its `QProcess::CrashExit` recovery path.
- Send at most one deliberate `SIGABRT`. If KWin does not recover, stop and
  report the state instead of retrying.
- KWin abandons the input method after 5 close crashes. Its crash counter
  resets after 20 seconds of stable runtime, so wait until the current
  supervisor has been stable for at least 20 seconds before the deliberate
  crash.

## 1. Verify The Installed Payload

Run the installed runtime check before replacing any process:

```bash
/opt/axidev-osk/bin/axidev-osk --verify-runtime
```

Read `/opt/axidev-osk/release.json` and report its version. Stop if the runtime
check fails or the expected version is not installed.

Record the SHA-256 of `~/.config/kwinrc` before continuing. If the file does
not exist, record that fact instead. The final state must match.

## 2. Identify The Secure Supervisor

Get the owner of the lock-screen service:

```bash
busctl --user status org.axidev.OSK.LockScreen
```

From that output, record the exact `PID`, assign it explicitly, and verify the
process before signaling it. Replace the example integer with the observed
value:

```bash
PID=12345
readlink -f "/proc/$PID/exe"
tr '\0' ' ' < "/proc/$PID/cmdline"
ps -o pid=,ppid=,etimes=,cmd= -p "$PID"
```

The command line must end with:

```text
internal plasma-lock-supervisor
```

If `/proc/$PID/exe` already resolves to
`/opt/axidev-osk/bin/axidev-osk`, the secure process already uses the current
payload. Do not crash it. Continue with the ordinary process.

If it resolves into `/opt/axidev-osk.old` or another replaced location, verify
that `etimes` is at least 20. Wait for the remaining time when necessary.

## 3. Replace The Secure Supervisor

Before sending the signal, state the exact PID, executable, command line, and
action. Ask for confirmation because this deliberately crashes a process and
creates a local crash report.

After confirmation, signal only the verified D-Bus owner:

```bash
kill -ABRT "$PID"
```

Wait up to 10 seconds for KWin to recreate the input method. Then run again:

```bash
busctl --user status org.axidev.OSK.LockScreen
pgrep -af axidev-osk
journalctl --user -u plasma-kwin_wayland.service --since "2 minutes ago" --no-pager
```

Record the new D-Bus owner as `NEW_PID`, then inspect only its children:

```bash
NEW_PID=23456
ps -o pid=,ppid=,etimes=,cmd= --ppid "$NEW_PID"
```

Require all of these results:

- the D-Bus owner has a different PID;
- its executable resolves to `/opt/axidev-osk/bin/axidev-osk`;
- its command line contains `internal plasma-lock-supervisor`;
- exactly one child runs `internal plasma-lock-worker`;
- KWin reports one `QProcess::CrashExit` followed by the new worker startup;
- no second crash or relaunch follows.

If any requirement fails, stop. Preserve the journal and report the observed
PIDs, executables, and errors. Do not send another signal.

## 4. Reload The Ordinary Application

The desktop application is managed separately by the generated autostart
service. If it is active, restart it once:

```bash
systemctl --user restart 'app-axidev\x2dosk@autostart.service'
systemctl --user status 'app-axidev\x2dosk@autostart.service' --no-pager
```

Verify that its new main PID runs `/usr/bin/python3 -I` with
`/opt/axidev-osk/libexec/launch.py`. If the service was not active before this
workflow, do not start it merely for verification.

## 5. Finish Verification

Wait until the new secure supervisor has remained stable for 20 seconds. Check
the D-Bus owner and process list one final time. Compare `~/.config/kwinrc`
with the recorded initial state. Confirm that no temporary Axidev OSK desktop
file was created under `~/.local/share/applications` and that `kwinrc` has the
same SHA-256, or remains absent if it started absent.

A process-level reload does not prove lock-screen input. When the change affects
secure input behavior, ask the user to perform one real lock and unlock cycle.
The user must confirm that the keyboard remains usable and that any virtual key
used to submit the password is released after unlock.

## Report The Result

State these facts explicitly:

- installed Axidev OSK and `axidev_io` versions;
- old and new secure supervisor PIDs and resolved executables;
- secure worker PID;
- ordinary application PID, or that it was inactive;
- whether KWin performed exactly one recovery;
- whether both new processes remained stable for 20 seconds;
- whether configuration files stayed unchanged;
- whether a real lock and unlock test passed, when required.
