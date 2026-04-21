import { contextBridge, ipcRenderer } from 'electron';

export type KeyboardWindowSize = {
  width: number;
  height: number;
};

contextBridge.exposeInMainWorld('keyboardWindow', {
  resizeToContent: (size: KeyboardWindowSize) => {
    ipcRenderer.send('keyboard:resize-to-content', size);
  },
});
