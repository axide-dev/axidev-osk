/// <reference types="vite/client" />

import type { KeyboardBridgeApi, KeyboardWindowApi } from './keyboard/shared';

declare global {
  interface Window {
    keyboardIO?: KeyboardBridgeApi;
    keyboardWindow?: KeyboardWindowApi;
  }
}

export {};
