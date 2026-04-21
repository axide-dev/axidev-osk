import { BrowserWindow, ipcMain } from 'electron';
import { keyboard, type KeyEvent } from '@axidev/io';
import { createListenerKeyIndex, getKeyBinding } from './keyBindings';
import type {
  KeyboardActionResult,
  KeyboardBridgeState,
  KeyboardPermissionState,
} from './shared';

const KEYBOARD_STATE_CHANNEL = 'keyboard:state-changed';
const KEYBOARD_GET_STATE_CHANNEL = 'keyboard:get-state';
const KEYBOARD_TAP_KEY_CHANNEL = 'keyboard:tap-key';
const KEYBOARD_PRESS_KEY_CHANNEL = 'keyboard:press-key';
const KEYBOARD_RELEASE_KEY_CHANNEL = 'keyboard:release-key';

const listenerKeyIndex = createListenerKeyIndex();
const pressedKeyIds = new Set<string>();
const latchedKeyIds = new Set<string>();

let permissions: KeyboardPermissionState | null = null;
let listenerStop: (() => void) | null = null;
let initializationAttempted = false;
let lastError: string | null = null;

function getLatchedModifierCount(modifier: string, excludeKeyId?: string): number {
  let count = 0;

  latchedKeyIds.forEach((keyId) => {
    if (keyId === excludeKeyId) {
      return;
    }

    const binding = getKeyBinding(keyId);

    if (binding?.kind === 'modifier' && binding.modifier === modifier) {
      count += 1;
    }
  });

  return count;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

function getState(): KeyboardBridgeState {
  const capabilities = keyboard.ready ? keyboard.getCapabilities() : null;

  return {
    ready: keyboard.ready,
    initialized: initializationAttempted,
    backendName: keyboard.ready ? keyboard.getBackendName() : null,
    version: keyboard.ready ? keyboard.version() : null,
    activeModifierNames: keyboard.ready
      ? keyboard.sender.getActiveModifierNames()
      : [],
    latchedKeyIds: Array.from(latchedKeyIds),
    pressedKeyIds: Array.from(pressedKeyIds),
    permissions,
    capabilities: capabilities
      ? {
          canInjectKeys: capabilities.canInjectKeys,
          canInjectText: capabilities.canInjectText,
          supportsKeyRepeat: capabilities.supportsKeyRepeat,
        }
      : null,
    error: lastError,
  };
}

function emitState(): void {
  const state = getState();

  BrowserWindow.getAllWindows().forEach((window) => {
    if (!window.isDestroyed()) {
      window.webContents.send(KEYBOARD_STATE_CHANNEL, state);
    }
  });
}

function clearError(): void {
  lastError = null;
}

function setError(error: unknown): void {
  lastError = getErrorMessage(error);
}

function stopListener(): void {
  if (!listenerStop) {
    return;
  }

  listenerStop();
  listenerStop = null;
}

function updatePressedKeys(event: KeyEvent): void {
  const matchedKeyIds = new Set<string>();

  if (event.keyName) {
    (listenerKeyIndex.get(event.keyName) ?? []).forEach((keyId) => {
      matchedKeyIds.add(keyId);
    });
  }

  if (event.combo) {
    (listenerKeyIndex.get(event.combo) ?? []).forEach((keyId) => {
      matchedKeyIds.add(keyId);
    });
  }

  if (matchedKeyIds.size === 0) {
    return;
  }

  matchedKeyIds.forEach((keyId) => {
    if (event.pressed) {
      pressedKeyIds.add(keyId);
      return;
    }

    pressedKeyIds.delete(keyId);
  });

  emitState();
}

function startListener(): void {
  if (!keyboard.ready || listenerStop) {
    return;
  }

  listenerStop = keyboard.listener.start((event) => {
    updatePressedKeys(event);
  });
}

function ensureReady(): boolean {
  if (keyboard.ready) {
    return true;
  }

  if (permissions?.requiresLogout) {
    lastError ??= 'Keyboard permissions were updated. Log out and back in, then relaunch the app.';
    return false;
  }

  try {
    initializationAttempted = true;
    keyboard.initialize({ keyDelayUs: 2000 });
    clearError();
    startListener();
    emitState();
    return true;
  } catch (error) {
    setError(error);
    emitState();
    return false;
  }
}

function actionResult(ok: boolean, error: string | null = null): KeyboardActionResult {
  return {
    ok,
    error,
    state: getState(),
  };
}

function toggleModifier(keyId: string): KeyboardActionResult {
  const binding = getKeyBinding(keyId);

  if (!binding || binding.kind !== 'modifier') {
    return actionResult(false, `Key "${keyId}" is not a modifier.`);
  }

  if (!ensureReady()) {
    return actionResult(false, lastError);
  }

  try {
    if (latchedKeyIds.has(keyId)) {
      if (getLatchedModifierCount(binding.modifier, keyId) === 0) {
        keyboard.sender.releaseModifiers(binding.modifier);
      }

      latchedKeyIds.delete(keyId);
    } else {
      if (getLatchedModifierCount(binding.modifier) === 0) {
        keyboard.sender.holdModifiers(binding.modifier);
      }

      latchedKeyIds.add(keyId);
    }

    clearError();
    emitState();
    return actionResult(true);
  } catch (error) {
    setError(error);
    emitState();
    return actionResult(false, lastError);
  }
}

function tapKey(keyId: string): KeyboardActionResult {
  const binding = getKeyBinding(keyId);

  if (!binding) {
    return actionResult(false, `No binding exists for "${keyId}".`);
  }

  if (binding.kind === 'unsupported') {
    return actionResult(false, binding.reason);
  }

  if (binding.kind === 'modifier') {
    return toggleModifier(keyId);
  }

  if (!ensureReady()) {
    return actionResult(false, lastError);
  }

  try {
    keyboard.sender.tap(binding.input);
    clearError();
    emitState();
    return actionResult(true);
  } catch (error) {
    setError(error);
    emitState();
    return actionResult(false, lastError);
  }
}

function pressKey(keyId: string): KeyboardActionResult {
  const binding = getKeyBinding(keyId);

  if (!binding || binding.kind !== 'key') {
    return actionResult(false, `Key "${keyId}" does not support press-and-hold.`);
  }

  if (!ensureReady()) {
    return actionResult(false, lastError);
  }

  try {
    keyboard.sender.keyDown(binding.input);
    clearError();
    emitState();
    return actionResult(true);
  } catch (error) {
    setError(error);
    emitState();
    return actionResult(false, lastError);
  }
}

function releaseKey(keyId: string): KeyboardActionResult {
  const binding = getKeyBinding(keyId);

  if (!binding || binding.kind !== 'key') {
    return actionResult(false, `Key "${keyId}" does not support press-and-hold.`);
  }

  if (!ensureReady()) {
    return actionResult(false, lastError);
  }

  try {
    keyboard.sender.keyUp(binding.input);
    clearError();
    emitState();
    return actionResult(true);
  } catch (error) {
    setError(error);
    emitState();
    return actionResult(false, lastError);
  }
}

function releaseLatchedModifiers(): void {
  if (!keyboard.ready) {
    latchedKeyIds.clear();
    return;
  }

  latchedKeyIds.forEach((keyId) => {
    const binding = getKeyBinding(keyId);

    if (binding?.kind === 'modifier') {
      keyboard.sender.releaseModifiers(binding.modifier);
    }
  });

  latchedKeyIds.clear();
}

export function initializeKeyboardService(): void {
  initializationAttempted = true;

  try {
    permissions = keyboard.setupPermissions();

    if (permissions.requiresLogout) {
      lastError = 'Keyboard permissions were updated. Log out and back in, then relaunch the app.';
      emitState();
      return;
    }

    keyboard.initialize({ keyDelayUs: 2000 });
    clearError();
    startListener();
  } catch (error) {
    setError(error);
  }

  emitState();
}

export function registerKeyboardIpc(): void {
  ipcMain.removeHandler(KEYBOARD_GET_STATE_CHANNEL);
  ipcMain.removeHandler(KEYBOARD_TAP_KEY_CHANNEL);
  ipcMain.removeHandler(KEYBOARD_PRESS_KEY_CHANNEL);
  ipcMain.removeHandler(KEYBOARD_RELEASE_KEY_CHANNEL);

  ipcMain.handle(KEYBOARD_GET_STATE_CHANNEL, () => getState());
  ipcMain.handle(KEYBOARD_TAP_KEY_CHANNEL, (_event, keyId: string) => tapKey(keyId));
  ipcMain.handle(KEYBOARD_PRESS_KEY_CHANNEL, (_event, keyId: string) => pressKey(keyId));
  ipcMain.handle(KEYBOARD_RELEASE_KEY_CHANNEL, (_event, keyId: string) =>
    releaseKey(keyId),
  );
}

export function shutdownKeyboardService(): void {
  pressedKeyIds.clear();

  try {
    stopListener();
    releaseLatchedModifiers();

    if (keyboard.ready) {
      keyboard.sender.releaseAllModifiers();
      keyboard.shutdown();
    }
  } catch (error) {
    setError(error);
  }

  emitState();
}
