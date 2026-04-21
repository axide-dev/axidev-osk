export type KeyboardWindowSize = {
  width: number;
  height: number;
};

export type KeyboardPermissionState = {
  platform: string;
  alreadyGranted: boolean;
  helperApplied: boolean;
  requiresLogout: boolean;
  helperPath: string | null;
};

export type KeyboardCapabilities = {
  canInjectKeys: boolean;
  canInjectText: boolean;
  supportsKeyRepeat: boolean;
};

export type KeyboardBridgeState = {
  ready: boolean;
  initialized: boolean;
  backendName: string | null;
  version: string | null;
  activeModifierNames: string[];
  latchedKeyIds: string[];
  pressedKeyIds: string[];
  permissions: KeyboardPermissionState | null;
  capabilities: KeyboardCapabilities | null;
  error: string | null;
};

export type KeyboardActionResult = {
  ok: boolean;
  error: string | null;
  state: KeyboardBridgeState;
};

export type KeyboardBridgeApi = {
  getState: () => Promise<KeyboardBridgeState>;
  tapKey: (keyId: string) => Promise<KeyboardActionResult>;
  pressKey: (keyId: string) => Promise<KeyboardActionResult>;
  releaseKey: (keyId: string) => Promise<KeyboardActionResult>;
  subscribe: (listener: (state: KeyboardBridgeState) => void) => () => void;
};

export type KeyboardWindowApi = {
  resizeToContent: (size: KeyboardWindowSize) => void;
};
