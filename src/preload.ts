import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';
import type {
  KeyboardActionResult,
  KeyboardBridgeApi,
  KeyboardBridgeState,
  KeyboardWindowApi,
  KeyboardWindowSize,
} from './keyboard/shared';

contextBridge.exposeInMainWorld('keyboardWindow', {
  resizeToContent: (size: KeyboardWindowSize) => {
    ipcRenderer.send('keyboard:resize-to-content', size);
  },
} satisfies KeyboardWindowApi);

contextBridge.exposeInMainWorld('keyboardIO', {
  getState: () => ipcRenderer.invoke('keyboard:get-state') as Promise<KeyboardBridgeState>,
  tapKey: (keyId: string) =>
    ipcRenderer.invoke('keyboard:tap-key', keyId) as Promise<KeyboardActionResult>,
  pressKey: (keyId: string) =>
    ipcRenderer.invoke('keyboard:press-key', keyId) as Promise<KeyboardActionResult>,
  releaseKey: (keyId: string) =>
    ipcRenderer.invoke('keyboard:release-key', keyId) as Promise<KeyboardActionResult>,
  subscribe: (listener: (state: KeyboardBridgeState) => void) => {
    const handleStateChange = (_event: IpcRendererEvent, state: KeyboardBridgeState) => {
      listener(state);
    };

    ipcRenderer.on('keyboard:state-changed', handleStateChange);

    return () => {
      ipcRenderer.removeListener('keyboard:state-changed', handleStateChange);
    };
  },
} satisfies KeyboardBridgeApi);
