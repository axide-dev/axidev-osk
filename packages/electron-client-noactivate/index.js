'use strict';

const path = require('node:path');
const { createRequire } = require('node:module');

const requireFromHere = createRequire(__filename);
const LOG_PREFIX = '[electron-client-noactivate]';
const LOG_LEVEL_ENV_VAR = 'ELECTRON_CLIENT_NOACTIVATE_LOG_LEVEL';
const LOG_LEVELS = Object.freeze({
  silent: 0,
  error: 1,
  warn: 2,
  info: 3,
  debug: 4,
});

let currentLogLevel = resolveLogLevel(process.env[LOG_LEVEL_ENV_VAR]);

function resolveLogLevel(value) {
  if (typeof value !== 'string') {
    return 'warn';
  }

  const normalized = value.trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(LOG_LEVELS, normalized)
    ? normalized
    : 'warn';
}

function shouldLog(level) {
  return LOG_LEVELS[level] <= LOG_LEVELS[currentLogLevel];
}

function log(level, message, details) {
  if (!shouldLog(level)) {
    return;
  }

  const line = `${LOG_PREFIX} ${message}`;

  if (details === undefined) {
    console[level](line);
    return;
  }

  console[level](line, details);
}

function createUnsupportedHandle() {
  log('info', `No-op install on unsupported platform ${process.platform}.`);

  return Object.freeze({
    dispose() {
      log('info', 'Ignoring dispose on unsupported platform.');
      return false;
    },
    installed: false,
    platform: process.platform,
    supported: false,
  });
}

function loadNativeModule() {
  const addonPath = path.join(
    __dirname,
    'build',
    'Release',
    'electron_client_noactivate.node',
  );

  try {
    log('info', `Loading native addon from ${addonPath}.`);
    return requireFromHere(addonPath);
  } catch (error) {
    throw new Error(`Failed to load native addon at ${addonPath}.`, {
      cause: error instanceof Error ? error : undefined,
    });
  }
}

const native = process.platform === 'win32' ? loadNativeModule() : null;

function assertBrowserWindow(window) {
  if (!window || typeof window.getNativeWindowHandle !== 'function') {
    throw new TypeError(
      'installNoActivateClientArea expects an Electron BrowserWindow instance.',
    );
  }
}

function getLogLevel() {
  return currentLogLevel;
}

function setLogLevel(level) {
  currentLogLevel = resolveLogLevel(level);
  process.env[LOG_LEVEL_ENV_VAR] = currentLogLevel;
  return currentLogLevel;
}

function installNoActivateClientArea(window) {
  assertBrowserWindow(window);
  log('info', 'Installing client-area no-activate hook.');

  if (process.platform !== 'win32') {
    return createUnsupportedHandle();
  }

  const hwnd = window.getNativeWindowHandle();
  let installed = false;
  let disposed = false;
  try {
    const summary = native.install(hwnd);
    installed = Boolean(summary?.installed);
    log('info', 'Native install summary.', summary);
  } catch (error) {
    log('error', 'Native install failed.', error);
  }

  return Object.freeze({
    dispose() {
      if (disposed) {
        return false;
      }

      disposed = true;

      if (typeof window.isDestroyed === 'function' && window.isDestroyed()) {
        log('warn', 'Skipping native uninstall because the window is already destroyed.');
        return false;
      }

      try {
        const summary = native.uninstall(hwnd);
        log('info', 'Native uninstall summary.', summary);
        return Boolean(summary?.installed);
      } catch (error) {
        log('error', 'Native uninstall failed.', error);
        return false;
      }
    },
    installed,
    platform: process.platform,
    supported: true,
  });
}

function isSupported() {
  return process.platform === 'win32';
}

module.exports = Object.freeze({
  getLogLevel,
  installNoActivateClientArea,
  isSupported,
  setLogLevel,
});
