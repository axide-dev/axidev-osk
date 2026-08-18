---
name: windows-dev-from-wsl
description: ALWAYS use this skill when working on Axidev OSK inside WSL. Use the Linux shell for orchestration and Git, but use Windows Python, Windows packages, Windows DLLs, and the Windows input backend for every runtime operation.
---

# Windows Development From WSL

Always follow this workflow when working on Axidev OSK inside WSL. The
application does not provide the required overlay behavior through WSL
Wayland. Use the Linux shell for orchestration and Git, but run every Python
operation with a Windows `python.exe`. A Linux process cannot load Windows
Python packages or DLLs, even when their files are visible from WSL.

## Runtime Rules

- Run commands from the repository root.
- Quote every path because Windows user paths may contain spaces.
- Use Linux Git to initialize the repository submodule.
- Use `.venv-windows/Scripts/python.exe` for Python, pip, imports, and startup.
- Convert repository paths with `wslpath -w` before passing them to Windows tools.
- Never activate `.venv-windows` from Linux.
- Never use Linux `python`, `python3`, `pip`, or `.venv/bin/python` in this workflow.
- Never set Linux `PYTHONPATH` for the Windows process.
- Never install packages into a discovered base interpreter.

## 1. Confirm WSL Interoperability

Check the interoperability handler and the explicit Windows command path:

```bash
test -r /proc/sys/fs/binfmt_misc/WSLInterop
grep -q '^enabled$' /proc/sys/fs/binfmt_misc/WSLInterop
CMD_EXE=/mnt/c/Windows/System32/cmd.exe
test -x "$CMD_EXE"
```

If a check fails, stop. Report which check failed. Do not edit `/etc/wsl.conf`
or restart WSL without the user's direction.

Windows commands do not need to be on the Linux `PATH`. Use their explicit
`/mnt/c/.../*.exe` paths.

## 2. Select a Standalone Windows Python

Ask Windows for every `python.exe`, then select the first standalone Python
3.10 or newer. Reject virtual environments so setup cannot modify another
application's environment.

```bash
WINDOWS_PYTHON=
while IFS= read -r windows_path; do
    windows_path=${windows_path%$'\r'}
    candidate=$(wslpath -u "$windows_path") || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.prefix == sys.base_prefix else 1)' </dev/null >/dev/null 2>&1; then
        WINDOWS_PYTHON=$candidate
        break
    fi
done < <("$CMD_EXE" /d /c where python 2>/dev/null)

test -n "$WINDOWS_PYTHON"
"$WINDOWS_PYTHON" -c 'import sys; print(sys.executable); print(sys.version); print(sys.platform)'
```

The final line must print `win32`. If no suitable interpreter exists, stop and
show the paths returned by `where python`. Do not select a rejected environment
or the Microsoft Store alias as a fallback.

## 3. Initialize the Input Backend

Use Linux Git because the checkout and its Git metadata belong to WSL:

```bash
git submodule update --init --recursive vendor/axidev-io-python
test -f vendor/axidev-io-python/pyproject.toml
```

If initialization fails, stop and report Git's error. Do not continue with an
empty backend directory.

## 4. Create the Windows Environment

Keep the Windows environment separate from the Linux `.venv`:

```bash
VENV_PYTHON="$PWD/.venv-windows/Scripts/python.exe"

if test -e .venv-windows && ! test -f "$VENV_PYTHON"; then
    printf '%s\n' '.venv-windows exists but is not a usable Windows environment.' >&2
    return 1 2>/dev/null || exit 1
fi

if ! test -e .venv-windows; then
    VENV_WINDOWS=$(wslpath -w "$PWD/.venv-windows")
    "$WINDOWS_PYTHON" -m venv "$VENV_WINDOWS"
fi

chmod +x .venv-windows/Scripts/*.exe
"$VENV_PYTHON" -c 'import sys; assert sys.platform == "win32"; print(sys.executable)'
```

If an existing environment fails validation, stop. Report its path. Do not
delete or recreate it without the user's direction.

## 5. Install Windows Packages

Pass Windows-form paths to Windows pip:

```bash
BACKEND_WINDOWS=$(wslpath -w "$PWD/vendor/axidev-io-python")
PROJECT_WINDOWS=$(wslpath -w "$PWD")

"$VENV_PYTHON" -m pip install \
    -e "$BACKEND_WINDOWS" \
    -e "$PROJECT_WINDOWS"
```

Do not retry a failed native build with Linux pip. Report the failing package,
the Windows Python version, and the complete build error.

## 6. Verify the Runtime Boundary

Verify the interpreter and all runtime imports before startup:

```bash
"$VENV_PYTHON" -c 'import sys, PySide6, axidev_io, axidev_osk; assert sys.platform == "win32"; print(sys.executable); print(PySide6.__version__)'
```

Passing verification proves that imports resolve through Windows Python. It
does not prove that the graphical application can start.

## 7. Start Axidev OSK

Keep the application attached when the user wants visible startup logs:

```bash
"$VENV_PYTHON" -m axidev_osk
```

For an agent-run startup check, capture logs and verify that the process stays
alive for three seconds:

```bash
STARTUP_LOG=$(mktemp -t axidev-osk-windows.XXXXXX.log)
"$VENV_PYTHON" -m axidev_osk >"$STARTUP_LOG" 2>&1 &
APP_PID=$!
sleep 3

if ! kill -0 "$APP_PID" 2>/dev/null; then
    wait "$APP_PID"
    status=$?
    printf 'Axidev OSK exited with status %s. Log: %s\n' "$status" "$STARTUP_LOG" >&2
    return "$status" 2>/dev/null || exit "$status"
fi

printf 'Axidev OSK is running as PID %s. Log: %s\n' "$APP_PID" "$STARTUP_LOG"
```

Leave the process running when the user asked to start the application. Stop
it after the check when the user asked only for verification.

## Report the Result

State these facts explicitly:

- the selected Windows base interpreter;
- the Windows virtual-environment interpreter;
- whether the submodule changed from uninitialized to initialized;
- whether installation and import verification passed;
- whether Axidev OSK stayed running;
- the process ID and startup log path, when applicable;
- the exact failed command and error, when any step fails.
