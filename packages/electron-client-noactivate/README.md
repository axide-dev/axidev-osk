# `@axidev/electron-client-noactivate`

Electron main-process helper for keeping a `BrowserWindow` usable without stealing focus
on ordinary client-area clicks.

This package is intentionally narrow:

- One main API: `installNoActivateClientArea(window)`
- Windows: native implementation
- Linux/macOS: stubbed no-op for now

## Install

```json
{
  "dependencies": {
    "@axidev/electron-client-noactivate": "file:packages/electron-client-noactivate"
  }
}
```

If this is consumed from a packaged Electron app, keep the native module external to the
main-process bundle and make sure the `.node` binary is shipped alongside the package.

## Main API

```ts
import { installNoActivateClientArea } from '@axidev/electron-client-noactivate';
```

```ts
const hook = installNoActivateClientArea(browserWindow);
```

`installNoActivateClientArea(window)` returns:

- `installed`: whether the platform-specific hook was installed
- `supported`: whether the current platform has a real implementation
- `platform`: current `process.platform`
- `dispose()`: removes the installed hook when possible

## Behavior

Current platform behavior:

- Windows: native implementation
- Linux: no-op stub
- macOS: no-op stub

Current Windows behavior:

- Client-area clicks are treated as non-activating as far as the top-level window hook
  can enforce.
- If Chromium or Electron still activates the window anyway, the package tracks the
  previously focused external window and restores focus back to it.
- Non-client clicks such as title-bar interactions are treated as intentional activation
  and are allowed through.

This means the Windows path is best described as:

- "Prefer no activation on client clicks"
- "Allow activation on window decoration clicks"
- "Restore previous foreground window if client activation still slips through"

It is a pragmatic Electron/Chromium workaround, not a guarantee of truly zero activation
latency.

## Recommended Usage

Call the installer once, from the Electron main process, after creating the window:

```ts
import { BrowserWindow } from 'electron';
import { installNoActivateClientArea } from '@axidev/electron-client-noactivate';

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 340,
  });

  const noActivateHook = installNoActivateClientArea(window);

  window.on('closed', () => {
    noActivateHook.dispose();
  });

  return window;
}
```

## Logging

The package supports these log levels:

- `silent`
- `error`
- `warn`
- `info`
- `debug`

Default log level: `warn`

You can control logs with either the environment variable or the exported setter:

```powershell
$env:ELECTRON_CLIENT_NOACTIVATE_LOG_LEVEL = 'info'
```

```ts
import { setLogLevel } from '@axidev/electron-client-noactivate';

setLogLevel('info');
```

The JS wrapper and the Windows native addon both use the same
`ELECTRON_CLIENT_NOACTIVATE_LOG_LEVEL` setting.

## Current Exports

- `installNoActivateClientArea(window)`
- `isSupported()`
- `getLogLevel()`
- `setLogLevel(level)`

## Limitations

- Linux and macOS are currently stubbed.
- On Windows, Chromium may still briefly activate the window before the focus-restore
  path runs.
- This package is designed for Electron main-process usage, not renderer usage.
